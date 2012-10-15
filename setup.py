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


with open("README") as readme:
    setup(
        name = "psh",
        version = "0.1",

        license = "GPL3",
        description = readme.readline().strip(),
        long_description = readme.read().strip(),
        url = "https://github.com/KonishchevDmitry/psh",

        author = "Dmitry Konishchev",
        author_email = "konishchev@gmail.com",

        packages = find_packages(),

        cmdclass = { "test": PyTest },
        tests_require = [ "pytest" ],
    )
