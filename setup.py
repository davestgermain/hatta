#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Hatta
=====

Hatta is a wiki engine – software that lets you run a wiki. It requires no
configuration and can be easily started in any Mercurial repository.

Hatta's pages are just plain text files (and also images, binaries, etc.) in
some directory in your repository. For example, you can put it in your
project's "docs" directory to keep documentation. The files can be edited both
from the wiki or with a text editor – in either case the changes committed to
the repository will appear in the recent changes and in page's history.

Usage
-----

Usage: hatta.py [options]

Options:
  -h, --help            show this help message and exit
  -d DIR, --pages-dir=DIR
                        Store pages in DIR
  -t DIR, --cache-dir=DIR
                        Store cache in DIR
  -i INT, --interface=INT
                        Listen on interface INT
  -p PORT, --port=PORT  Listen on port PORT
  -s NAME, --script-name=NAME
                        Override SCRIPT_NAME to NAME
  -n NAME, --site-name=NAME
                        Set the name of the site to NAME
  -m PAGE, --front-page=PAGE
                        Use PAGE as the front page
  -e ENC, --encoding=ENC
                        Use encoding ENS to read and write pages
  -c FILE, --config-file=FILE
                        Read configuration from FILE
  -l LANG, --language=LANG
                        Translate interface to LANG

"""

import hatta
from distutils.core import setup

setup(
    name='Hatta',
    version=hatta.__version__,
    url='http://hatta.sheep.art.pl/',
    download_url='http://devel.sheep.art.pl/hatta/zip/tip/',
    license='GNU General Public License (GPL)',
    author='Radomir Dopieralski',
    author_email='hatta@sheep.art.pl',
    description='Wiki engine that lives in Mercurial repository.',
    long_description=__doc__,
    keywords='wiki wsgi web mercurial repository',
    py_modules=['hatta'],
    #package_data={'hatta': ['locale/*']},
    data_files=[
        ('share/locale/pl/LC_MESSAGES', ['locale/pl/LC_MESSAGES/hatta.mo']),
        ('share/locale/ar/LC_MESSAGES', ['locale/ar/LC_MESSAGES/hatta.mo']),
        ('share/icons/icons/hicolor/scalable', ['hatta.svg']),
        ('share/doc/hatta/examples', ['hatta.fcg', 'hatta.wsgi']),
    ],
    scripts=['hatta-icon.py'],
    platforms='any',
    requires=['werkzeug (>=0.3)', 'pygments', 'mercurial (>=1.0)'],
    classifiers=[
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: System Administrators',
        'Topic :: Communications',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application',
        'Programming Language :: Python',
        'Operating System :: OS Independent',
        'Environment :: Web Environment',
    ]
)
