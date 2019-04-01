#!/usr/bin/env python
"""
Packaging script to create source packages and wheels.
Please don't use for installation. Use pip instead!
"""

from setuptools import setup, find_packages

setup(
    packages=find_packages('src'),
    package_dir={'': 'src'},
)
