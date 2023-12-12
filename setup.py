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
    test_suite='nose.collector',
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python",
        "Topic :: Internet",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    entry_points={
        'console_scripts': [
            'eventlet_chat_bridge_example = examples.chat_bridge:__main__',
            'eventlet_chat_server_example = examples.chat_server:__main__',
            'eventlet_connect_example = examples.connect:__main__',
            'eventlet_distributed_websocket_chat_example = examples.distributed_websocket_chat:__main__',
            'eventlet_echoserver_example = examples.echoserver:__main__',
            'eventlet_wsgi_example = examples.wsgi:__main__',
        ]
    }
)
