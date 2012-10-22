"""psh installation script."""

from __future__ import unicode_literals

from setuptools import find_packages, setup
from setuptools.command.test import test as Test


class PyTest(Test):
    def finalize_options(self):
        Test.finalize_options(self)
        self.test_args = [ "tests" ]
        self.test_suite = True

    def run_tests(self):
        import pytest
        pytest.main(self.test_args)


description = """\
psh allows you to spawn processes in Unix shell-style way.

Unix shell is very convenient for spawning processes, connecting them into
pipes, etc., but it has a very limited language which is often not suitable
for writing complex programs. Python is a very flexible and reach language
which is used in a wide variety of application domains, but its standard
subprocess module is very limited. psh combines the power of Python language
and an elegant shell-style way to execute processes.\
"""

setup(
    name = "psh",
    version = "0.2",

    license = "GPL3",
    description = "Process management library",
    long_description = description,
    url = "http://konishchevdmitry.github.com/psh/",

    author = "Dmitry Konishchev",
    author_email = "konishchev@gmail.com",

    packages = find_packages(),

    cmdclass = { "test": PyTest },
    tests_require = [ "pytest" ],
)
