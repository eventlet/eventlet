#!/usr/bin/env python
from setuptools import find_packages, setup
from eventlet import __version__
from os import path


setup(
    name='eventlet',
    version=__version__,
    description='Highly concurrent networking library',
    author='Linden Lab',
    author_email='eventletdev@lists.secondlife.com',
    url='http://eventlet.net',
    packages=find_packages(exclude=['benchmarks', 'tests', 'tests.*']),
    install_requires=(
        'enum-compat',
        'greenlet >= 0.3',
    ),
    zip_safe=False,
    long_description=open(
        path.join(
            path.dirname(__file__),
            'README.rst'
        )
    ).read(),
    test_suite='nose.collector',
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Topic :: Internet",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Intended Audience :: Developers",
        "Development Status :: 4 - Beta",
    ]
)
