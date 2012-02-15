#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

import hatta

################### Common settings ######################

config = dict(
    name=hatta.project_name,
    version=hatta.__version__,
    url=hatta.project_url,
    download_url='http://download.hatta-wiki.org/hatta-%s/Hatta-%s.zip' % (
        hatta.__version__, hatta.__version__),
    license='GNU General Public License (GPL)',
    author='Radomir Dopieralski',
    author_email='hatta@sheep.art.pl',
    description=hatta.project_description,
    long_description=hatta.__doc__,
    keywords='wiki wsgi web mercurial repository',
    py_modules=['hatta'],
    data_files=[
        ('share/locale/ar/LC_MESSAGES', ['locale/ar/LC_MESSAGES/hatta.mo']),
        ('share/locale/da/LC_MESSAGES', ['locale/da/LC_MESSAGES/hatta.mo']),
        ('share/locale/de/LC_MESSAGES', ['locale/de/LC_MESSAGES/hatta.mo']),
        ('share/locale/es/LC_MESSAGES', ['locale/es/LC_MESSAGES/hatta.mo']),
        ('share/locale/fr/LC_MESSAGES', ['locale/fr/LC_MESSAGES/hatta.mo']),
        ('share/locale/ja/LC_MESSAGES', ['locale/ja/LC_MESSAGES/hatta.mo']),
        ('share/locale/pl/LC_MESSAGES', ['locale/pl/LC_MESSAGES/hatta.mo']),
        ('share/locale/sv/LC_MESSAGES', ['locale/sv/LC_MESSAGES/hatta.mo']),
        ('share/icons/hicolor/scalable', ['resources/hatta.svg']),
        ('share/icons/hicolor/64x64', ['resources/hatta.png']),
        ('share/doc/hatta/examples', [
            'examples/hatta.fcg',
            'examples/hatta.wsgi',
            'examples/extend_parser.py'
        ]),
    ],
    platforms='any',
    install_requires=['werkzeug >=0.3', 'mercurial >=1.0'],
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
    ],
)

if __name__ == '__main__':
    setup(**config)
