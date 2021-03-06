#!/usr/bin/env python
"""
$Id$
see http://peak.telecommunity.com/DevCenter/setuptools

note: if you want to develop this code and run from code on the command line,
please run the following line when you update to a new version of the code.
python setup.py develop --install-dir=$HOME/Library/Python

distribution:
python setup.py develop --install-dir=$HOME/Library/Python
python setup.py sdist
python setup.py bdist_egg
(cd dist; rsync -Cuav * larch.ssec.wisc.edu:/var/apache/larch/htdocs/eggs/repos/uwglance)

use: 
python setup.py install --install-dir=$HOME/Library/Python
easy_install -d $HOME/Library/Python -vi http://larch.ssec.wisc.edu/eggs/repos uwglance
"""

# changed to support egg distribution
from setuptools import setup, find_packages

setup( name="uwglance", 
       version="0.3.3",
       zip_safe = False,
       entry_points = { 'console_scripts': [ 'glance = glance.compare:main' ] },
       packages = ['glance'], #find_packages('.'),
       install_requires=[ 'numpy', 'matplotlib', 'basemap', 'scipy', 'mako>=0.4.1' ],
       package_data = {'': ['*.txt', '*.gif']}
       )

