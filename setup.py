import sys
from setuptools import setup

if sys.version_info < (3, 5, 2):
    raise RuntimeError('Python < 3.5.2 is not supported')

setup(
    name='http',
    version='0.0.0',
    description=('Asynchronous HTTP client/server framework for '
                 'asyncio and Python.'),
    author='Oshinko',
    author_email='osnk@renjaku.jp',
    url='https://github.com/oshinko/pyhttp',
    packages=['osnk.http'],
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: Implementation :: CPython'
    ]
)
