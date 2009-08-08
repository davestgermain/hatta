#!/usr/bin/env python
# -*- coding: utf-8 -*-

from distutils.core import setup
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
        ('share/icons/hicolor/scalable', ['resources/hatta.svg']),
        ('share/icons/hicolor/32x32', ['resources/hatta.png']),
        ('share/applications', ['resources/hatta.desktop']),
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
    options = {
        'py2exe': {
            'packages': ['werkzeug', 'dbhash', 'encodings'],
            'excludes': ['_ssl', 'tcl', 'tkinter'],
            'dll_excludes': ['tcl84.dll', 'tk84.dll'],
            "compressed": 1,
            "optimize": 2,
        },
        'py2app': {
            'argv_emulation': True,
            'includes': ['werkzeug.routing', 'PyQt4.QtGui',
                'PyQt4.QtCore', 'PyQt4._qt', 'sip'],
            'iconfile': 'resources/hatta.icns',
            'resources': ['hatta.py'],
        },
    },
# for Mac
    app=['hatta_qticon.py'],
)

if platform == 'darwin':
    from setuptools import setup
    config['setup_requires'] = ['py2app']
elif platform == 'win32':
    ### Windows installer ###
    class BuildInstaller(py2exe.build_exe.py2exe):
        """
           This class first builds the exe file(s),
           then creates a Windows installer.
           You need InnoSetup for it.
        """
        def run(self):
            # First, let py2exe do it's work.
            py2exe.build_exe.py2exe.run(self)
            lib_dir = self.lib_dir
            dist_dir = self.dist_dir
            # create the Installer, using the files py2exe has created.
            script = InnoScript("hatta", lib_dir, dist_dir,
                                self.console_exe_files+self.windows_exe_files,
                                self.lib_files)
            print "*** creating the inno setup script***"
            script.create()
            print "*** compiling the inno setup script***"
            script.compile()
            # Note: By default the final setup.exe will be in an
            # Output subdirectory.
    config['cmdclass'] = {"py2exe-installer": BuildInstaller}
    config['console'] = [{
        'script': 'hatta.py',
        'icon_resources': [(1, "resources/hatta.ico")],
    }],
else: # Other UNIX-like
    config['scripts'] = ['hatta_qticon.py', 'hatta_gtkicon.py']

setup(**config)
