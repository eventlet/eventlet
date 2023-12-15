#!/usr/bin/env python
import os
import setuptools


os.environ.setdefault('EVENTLET_IMPORT_VERSION_ONLY', '1')
import eventlet

setuptools.setup(
    name='eventlet',
    version=eventlet.__version__,
    description='Highly concurrent networking library',
    author='Linden Lab',
    author_email='eventletdev@lists.secondlife.com',
    url='http://eventlet.net',
    python_requires=">=3.8.0",
    project_urls={
        'Source': 'https://github.com/eventlet/eventlet',
    },
    packages=setuptools.find_packages(exclude=['benchmarks', 'tests', 'tests.*']),
    install_requires=(
        'dnspython >= 1.15.0',
        'greenlet >= 1.0',
        'monotonic >= 1.4;python_version<"3.5"',
        'six >= 1.10.0',
    ),
    zip_safe=False,
    long_description=open(
        os.path.join(
            os.path.dirname(__file__),
            'README.rst'
        )
    ).read(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python",
        "Topic :: Internet",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ]
)
