from setuptools import find_packages, setup

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
    )
