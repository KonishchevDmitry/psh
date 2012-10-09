# -*- coding: utf-8 -*-

"""Tests I/O redirection."""

from __future__ import unicode_literals

import logging
import tempfile

from psh import sh
from psh import File, STDOUT, STDERR, DEVNULL

import test
test.init(globals())


def test_stdin_from_file(test, capfd):
    """Tests redirecting a file to stdin."""

    logging.disable(logging.CRITICAL)

    try:
        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(b"test\nтест")
            temp_file.flush()

            process = sh.tr("t", "z", _stdin = File(temp_file.name)).execute()

            assert process.stdout() == "zesz\nтест"
            assert process.stderr() == ""

            stdout, stderr = capfd.readouterr()
            assert stdout == ""
            assert stderr == ""
    finally:
        logging.disable(logging.NOTSET)


def test_stdout(test, capfd):
    """Tests output to stdout."""

    logging.disable(logging.CRITICAL)

    try:
        process = sh.sh("-c", "echo test1; echo test2 >&2; echo тест3; echo тест4 >&2;", _stdout = STDOUT)
        process.execute()

        assert process.stdout() == ""
        assert process.stderr() == "test2\nтест4\n"

        stdout, stderr = capfd.readouterr()
        assert stdout == "test1\nтест3\n"
        assert stderr == ""
    finally:
        logging.disable(logging.NOTSET)


def test_stderr(test, capfd):
    """Tests output to stderr."""

    logging.disable(logging.CRITICAL)

    try:
        process = sh.sh("-c", "echo test1; echo test2 >&2; echo тест3; echo тест4 >&2;", _stderr = STDERR)
        process.execute()

        assert process.stdout() == "test1\nтест3\n"
        assert process.stderr() == ""

        stdout, stderr = capfd.readouterr()
        assert stdout == ""
        assert stderr == "test2\nтест4\n"
    finally:
        logging.disable(logging.NOTSET)


def test_stdout_to_stderr_redirection(test, capfd):
    """Tests redirection of stdout to stderr."""

    logging.disable(logging.CRITICAL)

    try:
        process = sh.sh("-c", "echo test1; echo test2 >&2; echo тест3; echo тест4 >&2;", _stdout = STDERR)
        process.execute()

        assert process.stdout() == ""
        assert process.stderr() == "test1\ntest2\nтест3\nтест4\n"

        stdout, stderr = capfd.readouterr()
        assert stdout == ""
        assert stderr == ""
    finally:
        logging.disable(logging.NOTSET)


def test_stderr_to_stdout_redirection(test, capfd):
    """Tests redirection of stderr to stdout."""

    logging.disable(logging.CRITICAL)

    try:
        process = sh.sh("-c", "echo test1; echo test2 >&2; echo тест3; echo тест4 >&2;", _stderr = STDOUT)
        process.execute()

        assert process.stdout() == "test1\ntest2\nтест3\nтест4\n"
        assert process.stderr() == ""

        stdout, stderr = capfd.readouterr()
        assert stdout == ""
        assert stderr == ""
    finally:
        logging.disable(logging.NOTSET)


def test_stdout_and_stderr(test, capfd):
    """Tests output to stdout and stderr."""

    logging.disable(logging.CRITICAL)

    try:
        process = sh.sh("-c", "echo test1; echo test2 >&2; echo тест3; echo тест4 >&2;", _stdout = STDOUT, _stderr = STDERR)
        process.execute()

        assert process.stdout() == ""
        assert process.stderr() == ""

        stdout, stderr = capfd.readouterr()
        assert stdout == "test1\nтест3\n"
        assert stderr == "test2\nтест4\n"
    finally:
        logging.disable(logging.NOTSET)


def test_stdout_to_file_and_stderr_to_dev_null(test, capfd):
    """Tests redirection of stdout to a file and stderr to /dev/null."""

    logging.disable(logging.CRITICAL)

    try:
        with tempfile.NamedTemporaryFile() as temp_file:
            process = sh.sh("-c", "echo test1; echo test2 >&2; echo тест3; echo тест4 >&2;",
                _stdout = File(temp_file.name), _stderr = DEVNULL)
            process.execute()

            assert process.stdout() == ""
            assert process.stderr() == ""

            stdout, stderr = capfd.readouterr()
            assert stdout == ""
            assert stderr == ""

            assert temp_file.read() == b"test1\nтест3\n"
    finally:
        logging.disable(logging.NOTSET)


def test_stdout_to_dev_null_and_stderr_to_file(test, capfd):
    """Tests redirection of stdout to /dev/null and stderr to a file."""

    logging.disable(logging.CRITICAL)

    try:
        with tempfile.NamedTemporaryFile() as temp_file:
            process = sh.sh("-c", "echo test1; echo test2 >&2; echo тест3; echo тест4 >&2;",
                _stdout = DEVNULL, _stderr = File(temp_file.name))
            process.execute()

            assert process.stdout() == ""
            assert process.stderr() == ""

            stdout, stderr = capfd.readouterr()
            assert stdout == ""
            assert stderr == ""

            assert temp_file.read() == b"test2\nтест4\n"
    finally:
        logging.disable(logging.NOTSET)


def test_stdout_to_file_with_append(test, capfd):
    """Tests redirection of stdout to to a file with appending."""

    logging.disable(logging.CRITICAL)

    try:
        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write("orig\n")
            temp_file.flush()

            process = sh.sh("-c", "echo test1; echo test2 >&2; echo тест3; echo тест4 >&2;",
                _stdout = File(temp_file.name, append = True))
            process.execute()

            assert process.stdout() == ""
            assert process.stderr() == "test2\nтест4\n"

            stdout, stderr = capfd.readouterr()
            assert stdout == ""
            assert stderr == ""

            with open(temp_file.name) as stdout:
                assert stdout.read() == b"orig\ntest1\nтест3\n"
    finally:
        logging.disable(logging.NOTSET)


def test_stderr_to_file_with_append(test, capfd):
    """Tests redirection of stderr to to a file with appending."""

    logging.disable(logging.CRITICAL)

    try:
        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write("orig\n")
            temp_file.flush()

            process = sh.sh("-c", "echo test1; echo test2 >&2; echo тест3; echo тест4 >&2;",
                _stderr = File(temp_file.name, append = True))
            process.execute()

            assert process.stdout() == "test1\nтест3\n"
            assert process.stderr() == ""

            stdout, stderr = capfd.readouterr()
            assert stdout == ""
            assert stderr == ""

            with open(temp_file.name) as stderr:
                assert stderr.read() == b"orig\ntest2\nтест4\n"
    finally:
        logging.disable(logging.NOTSET)
