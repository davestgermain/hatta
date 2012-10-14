#!/usr/bin/env python
# -*- coding: utf-8 -*-

import setuptools


################### Common settings ######################

setuptools.setup(
    name='Hatta',
    version='1.5.1',
    license='GNU General Public License (GPL)',
    author='Radomir Dopieralski',
    author_email='hatta@sheep.art.pl',
    keywords='wiki wsgi web mercurial repository',
    packages=['hatta'],
    install_requires=[
        'distribute',
        'werkzeug >=0.3',
        'mercurial >=1.0',
        'jinja2',
#        'pygments',
    ],
    tests_require=['py.test'],
    data_files=[
        ('share/locale/ar/LC_MESSAGES', ['locale/ar/LC_MESSAGES/hatta.mo']),
        ('share/locale/da/LC_MESSAGES', ['locale/da/LC_MESSAGES/hatta.mo']),
        ('share/locale/de/LC_MESSAGES', ['locale/de/LC_MESSAGES/hatta.mo']),
        ('share/locale/es/LC_MESSAGES', ['locale/es/LC_MESSAGES/hatta.mo']),
        ('share/locale/fr/LC_MESSAGES', ['locale/fr/LC_MESSAGES/hatta.mo']),
        ('share/locale/ja/LC_MESSAGES', ['locale/ja/LC_MESSAGES/hatta.mo']),
        ('share/locale/pl/LC_MESSAGES', ['locale/pl/LC_MESSAGES/hatta.mo']),
        ('share/locale/sv/LC_MESSAGES', ['locale/sv/LC_MESSAGES/hatta.mo']),
        ('share/doc/hatta/examples', [
            'examples/hatta.fcg',
            'examples/hatta.wsgi',
            'examples/extend_parser.py'
        ]),
    ],
    include_package_data=True,
    zip_safe=True,
    platforms='any',
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
