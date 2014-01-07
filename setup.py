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
        'matplotlib==1.3.1',
        'numpy==1.8.0',
        'obsub==0.1.1',
        'pydicti==0.0.2',
        'PyMAD==0.4',
        'unum==4.1.3',
        'wxPython==2.8.12.1',
    ],
    entry_points={
        'gui_scripts': ['madgui = madgui.main:main'],
    },
    package_data={
        'madgui': ['resource/*']
    }
)
