#!/usr/bin/env python

from setuptools import setup

setup(
    name='eventlet',
    version='0.2',
    description='Coroutine-based networking library',
    author='Linden Lab',
    author_email='eventletdev@lists.secondlife.com',
    url='http://wiki.secondlife.com/wiki/Eventlet',
    packages=['eventlet'],
    install_requires=['greenlet'],
    long_description="""
    Eventlet is a networking library written in Python. It achieves
    high scalability by using non-blocking io while at the same time
    retaining high programmer usability by using coroutines to make
    the non-blocking io operations appear blocking at the source code
    level.""",
    classifiers=[
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python",
    "Topic :: Internet",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Intended Audience :: Developers",
    "Development Status :: 4 - Beta"]
    )

