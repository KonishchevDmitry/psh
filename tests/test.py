# -*- coding: utf-8 -*-

"""Common test utils."""

from __future__ import unicode_literals

import os
import platform
import re
import subprocess
import threading

import psys
import psh


def check_leaks(request):
    """Test wrapper that checks the module for leaks."""

    def opened_fds():
        if platform.system() == "Darwin":
            fd_path = "/dev/fd"
        else:
            fd_path = "/proc/self/fd"

        return set( int(fd) for fd in os.listdir(fd_path) )

    def running_threads():
        return set( thread.ident for thread in threading.enumerate() )

    def process_childs():
        process = subprocess.Popen(
            [ "ps", "-A", "-o", "ppid=,pid=,command=" ],
            stdout = subprocess.PIPE)

        stdout = psys.u(process.communicate()[0])
        assert not process.returncode
        assert stdout

        childs = ""

        for line in stdout.split("\n"):
            match = re.search(r"^\s*{0}\s+(\d+)".format(os.getpid()), line)

            if match is not None and int(match.group(1)) != process.pid:
                if childs:
                    childs += "\n"

                childs += line

        return childs

    fds = opened_fds()
    threads = running_threads()
    childs = process_childs()

    def check():
        assert opened_fds() == fds
        assert running_threads() == threads
        assert process_childs() == childs

    request.addfinalizer(check)


def init(globals):
    """Initializes the test."""

    # Notify the module that it's under unit testing
    psh._UNIT_TEST = True

    globals["pytest_funcarg__test"] = check_leaks

    try:
        import pycl.log
    except ImportError:
        pass
    else:
        pycl.log.setup(debug_mode = True)
