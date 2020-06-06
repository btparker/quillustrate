#!/usr/bin/env python
import setuptools
from distutils.core import setup

setup(
    name='quillustrate',
    version='0.1',
    description='Means of using Quill in various 3D pipelines',
    author='Tyler Parker',
    author_email='btylerparker@gmail.com',
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
