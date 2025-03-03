# -*- coding: utf-8 -*-

# This code is part of Qiskit.
#
# (C) Copyright IBM 2022.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Setup qiskit_ibm_experiment"""

import os

import setuptools

REQUIREMENTS = [
    "qiskit-terra>=0.18.0",
    "requests>=2.19",
    "requests-ntlm>=1.1.0",
    "numpy>=1.13",
    "urllib3>=1.21.1",
    "python-dateutil>=2.8.0",
    "typing-extensions>=4.0.0",  # remove when support for Python 3.7 is dropped (use "from typing import" instead)
]

# Handle version.
VERSION_PATH = os.path.join(
    os.path.dirname(__file__), "qiskit_ibm_experiment", "VERSION.txt"
)
with open(VERSION_PATH, "r") as version_file:
    VERSION = version_file.read().strip()

# Read long description from README.
README_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "README.md")
with open(README_PATH) as readme_file:
    README = readme_file.read()


setuptools.setup(
    name="qiskit-ibm-experiment",
    version=VERSION,
    description="Qiskit IBM Experiment service for accessing the quantum experiment "
    "interface at IBM",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/Qiskit/qiskit-ibm-experiment",
    author="Qiskit Development Team",
    author_email="hello@qiskit.org",
    license="Apache 2.0",
    classifiers=[
        "Environment :: Console",
        "License :: OSI Approved :: Apache Software License",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Scientific/Engineering",
    ],
    keywords="qiskit sdk quantum api experiment ibm",
    packages=setuptools.find_packages(exclude=["test*"]),
    install_requires=REQUIREMENTS,
    include_package_data=True,
    python_requires=">=3.7",
    zip_safe=False,
    project_urls={
        "Bug Tracker": "https://github.com/Qiskit/qiskit-ibm-experiment/issues",
        "Documentation": "https://qiskit.org/documentation/",
        "Source Code": "https://github.com/Qiskit/qiskit-ibm-experiment",
    },
)
