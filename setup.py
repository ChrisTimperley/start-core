import os
import glob
import setuptools

PKG_NAME = 'start_th'

path = os.path.join(os.path.dirname(__file__), 'src', PKG_NAME, 'version.py')
with open(path, 'r') as f:
    exec(f.read())

setuptools.setup(
    name=PKG_NAME,
    version=__version__,
    description='A test harness for START',
    long_description='TBA',
    author='Chris Timperley',
    author_email='christimperley@gmail.com',
    url='https://github.com/ChrisTimperley/start-test-harness',
    # python_requires='>=3.5',
    install_requires=[
        'configparser',
        'attrs'
    ],
    packages=['start_th'],
    package_dir={'': 'src'},
    entry_points = {
        'console_scripts': [ 'start-tester = start_th.cli:main' ]
    }
)
