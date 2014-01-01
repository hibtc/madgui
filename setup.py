#!/usr/bin/env python
# encoding: utf-8

from setuptools import setup

setup(
    name='madgui',
    version='0.2',
    description='GUI for beam simulation using MadX via PyMad',
    long_description=open('README.rst').read(),
    author='Thomas Gläßle',
    author_email='t_glaessle@gmx.de',
    maintainer='Thomas Gläßle',
    maintainer_email='t_glaessle@gmx.de',
    url='https://github.com/coldfix/madgui',
    packages=['madgui'],
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
    install_requires=[
        'pydicti',
        'obsub',
        'PyMAD',
        'unum',
    ],
    entry_points={
        'gui_scripts': [
            'madgui = madgui.main:main'
        ],
    },
    package_data={
        'madgui': ['resource/*']
    }
)
