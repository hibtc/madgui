#!/usr/bin/env python
# encoding: utf-8

from setuptools import setup

# Read README.rst for PyPI
# you should convert it by hand like so: pandoc README.md -o README.rst
try:
    f = open('README.rst')
    long_description = f.read()
    f.close()
except:
    long_description = None


setup(name='madgui',
    version='0.0.1',
    description='GUI for beam simulation using MadX via PyMad',
    long_description=long_description,
    author='Thomas Gläßle',
    author_email='t_glaessle@gmx.de',
    maintainer='Thomas Gläßle',
    maintainer_email='t_glaessle@gmx.de',
    url=None,
    packages=['madgui',],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Healthcare Industry',
        'Intended Audience :: Science/Research',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Scientific/Engineering :: Medical Science Apps.',
        'Topic :: Scientific/Engineering :: Physics',
    ],
    license=None,
    test_suite='nose.collector',
    install_requires=['pydicti','PyMAD',],
    )
