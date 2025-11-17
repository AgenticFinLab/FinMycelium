import io
import os
import re

import setuptools


def get_long_description():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    with io.open(os.path.join(base_dir, "description.txt"), encoding="utf-8") as f:
        return f.read()


def get_requirements():
    with open("requirements.txt") as f:
        return f.read().splitlines()


def get_version():
    current_dir = os.path.abspath(os.path.dirname(__file__))
    version_file = os.path.join(current_dir, "cdemo", "__init__.py")
    with io.open(version_file, encoding="utf-8") as f:
        return re.search(r'^__version__ = [\'"]([^\'"]*)[\'"]', f.read(), re.M).group(1)


setuptools.setup(
    name="python-coding-template",
    version=get_version(),
    author="",
    license="Apache-2.0",
    description="Packaged version of financial trend tracer for visual language models",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/AgenticFin/python-coding-structure",
    packages=setuptools.find_packages(exclude=["tests"]),
    python_requires=">=3.11",
    install_requires=get_requirements(),
    extras_require={"tests": ["pytest"]},
    include_package_data=True,
    options={"bdist_wheel": {"python_tag": "py311"}},
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Education",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    keywords="python-coding, template",
)
