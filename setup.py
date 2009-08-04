#!/usr/bin/env python
# -*- coding: utf-8 -*-

#from distutils.core import setup
from setuptools import setup
from sys import platform

import hatta

################### Common settings ######################

config = dict(
    name='Hatta',
    version=hatta.__version__,
    url='http://hatta.sheep.art.pl/',
    download_url='http://sheep.art.pl/misc/hatta-%s/Hatta-%s.zip' % (
        hatta.__version__, hatta.__version__),
    license='GNU General Public License (GPL)',
    author='Radomir Dopieralski',
    author_email='hatta@sheep.art.pl',
    description='Wiki engine that lives in Mercurial repository.',
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
        ('share/icons/hicolor/scalable', ['hatta.svg']),
        ('share/applications', ['hatta.desktop']),
        ('share/doc/hatta/examples', [
            'examples/hatta.fcg',
            'examples/hatta.wsgi',
            'examples/extend_parser.py'
        ]),
    ],
    platforms='any',
    requires=['werkzeug (>=0.3)', 'mercurial (>=1.0)'],
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

if platform == 'darwin':
    py2app_config = dict(
            app=['hatta_qticon.py'],
            options={'py2app': {
                'argv_emulation': True,
                'includes': ['werkzeug.routing', 'PyQt4.QtGui', 
                    'PyQt4.QtCore', 'PyQt4._qt'],
                'iconfile': 'hatta.icns',
                        }},
            setup_requires=['py2app'],
    )
    config.update(**py2app_config)
elif platform == 'win32':
    from exe_setup import build_installer
    py2exe_config = dict(
        cmdclass = {"py2exe": build_installer},
        options = {'py2exe': {
            'packages': ['werkzeug', 'dbhash', 'encodings'],
            'excludes': ['_ssl', 'tcl', 'tkinter'],
            'dll_excludes': ['tcl84.dll', 'tk84.dll'],
            "compressed": 1,
            "optimize": 2,
        }},
        console = [{
            'script': 'hatta.py',
            'icon_resources': [(1, "hatta.ico")],
        }],
    )
    config.update(**py2exe_config)
else: # Other UNIX-like
    unix_config = dict(
            scripts=['hatta_qticon.py'],
            )
    config.update(**unix_config)

setup(**config)

