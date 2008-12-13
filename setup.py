#!/usr/bin/env python
# -*- coding: utf-8 -*-

from distutils.core import setup
import hatta

setup(
    name='Hatta',
    version=hatta.__version__,
    url='http://hatta.sheep.art.pl/',
    download_url='http://devel.sheep.art.pl/hatta/archive/tip.zip',
    license='GNU General Public License (GPL)',
    author='Radomir Dopieralski',
    author_email='hatta@sheep.art.pl',
    description='Wiki engine that lives in Mercurial repository.',
    long_description=hatta.__doc__,
    keywords='wiki wsgi web mercurial repository',
    py_modules=['hatta', 'hatta_jp'],
    data_files=[
        ('share/locale/pl/LC_MESSAGES', ['locale/pl/LC_MESSAGES/hatta.mo']),
        ('share/locale/ar/LC_MESSAGES', ['locale/ar/LC_MESSAGES/hatta.mo']),
        ('share/icons/hicolor/scalable', ['hatta.svg']),
        ('share/applications', ['hatta.desktop']),
        ('share/doc/hatta/examples', ['hatta.fcg', 'hatta.wsgi']),
    ],
    scripts=['hatta-icon.py'],
    platforms='any',
    requires=['werkzeug (>=0.3)', 'mercurial (>=1.0)'],
    extras_require={
        'highlight': ['pygments'],
        'hatta-icon': ['pygtk'],
    },
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
