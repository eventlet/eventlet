#!/usr/bin/env python


from setuptools import find_packages, setup
from eventlet import __version__
import sys

requirements = []
for flag, req in [('--without-greenlet','greenlet >= 0.2'),
                  ('--without-pyopenssl', 'pyopenssl')]:
    if flag in sys.argv:
        sys.argv.remove(flag)
    else:
        requirements.append(req)

setup(
    name='eventlet',
    version=__version__,
    description='Coroutine-based networking library',
    author='Linden Lab',
    author_email='eventletdev@lists.secondlife.com',
    url='http://eventlet.net',
    packages=find_packages(exclude=['tests']),
    install_requires=requirements,
    long_description="""
    Eventlet is a networking library written in Python. It achieves
    high scalability by using non-blocking io while at the same time
    retaining high programmer usability by using coroutines to make
    the non-blocking io operations appear blocking at the source code
    level.""",
    test_suite = 'nose.collector',
    classifiers=[
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python",
    "Operating System :: MacOS :: MacOS X",
    "Operating System :: POSIX",
    "Operating System :: Microsoft :: Windows",
    "Topic :: Internet",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Intended Audience :: Developers",
    "Development Status :: 4 - Beta"]
    )

