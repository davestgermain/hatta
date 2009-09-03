#!/usr/bin/env python
# -*- coding: utf-8 -*-

from distutils.core import setup

import sys
import os

import hatta

################### Common settings ######################

config = dict(
    name=hatta.name,
    version=hatta.__version__,
    url=hatta.url,
    download_url='http://download.hatta-wiki.org/hatta-%s/Hatta-%s.zip' % (
        hatta.__version__, hatta.__version__),
    license='GNU General Public License (GPL)',
    author='Radomir Dopieralski',
    author_email='hatta@sheep.art.pl',
    description=hatta.description,
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
        ('share/applications', ['resources/hatta.desktop']),
        ('share/doc/hatta/examples', [
            'examples/hatta.fcg',
            'examples/hatta.wsgi',
            'examples/extend_parser.py'
        ]),
    ],
    platforms='any',
    requires=['werkzeug (>=0.3)', 'mercurial (>=1.0)',
             'pybonjour (>=1.1.1)'],
    setup_requires = ['pybonjour'],
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
			'includes': ['sip'],
            'packages': ['werkzeug', 'dbhash', 'encodings'],
            'excludes': ['_ssl', 'tcl', 'tkinter', 'Tkconstants' 
                         ,'Tkinter'],
            'dll_excludes': ['tcl84.dll', 'tk84.dll'],
            "compressed": 1,
            "optimize": 2,
			"bundle_files": 1,
        },
        'py2app': {
            'argv_emulation': True,
# When packaging with MacPorts PyQt add to includes:
# PyQt4._qt
# See README-MAC
            'iconfile': 'resources/hatta.icns',
            'resources': ['hatta.py'],
            'includes': ['sip', 'PyQt4', 'PyQt4.QtCore', 'PyQt4.QtGui'],
            'excludes': ['PyQt4.QtDesigner', 'PyQt4.QtNetwork', 
                         'PyQt4.QtOpenGL', 'PyQt4.QtScript', 'PyQt4.QtSql', 
                         'PyQt4.QtTest', 'PyQt4.QtWebKit', 'PyQt4.QtXml', 
                         'PyQt4.phonon'],
        },
    },
)

if sys.platform == 'darwin':
    from setuptools import setup
    config['setup_requires'].append('py2app')
    config['app'] = ['hatta_qticon.py']

    # Add deleting Qt debug libs (like QtCore_debug) to the py2app build 
    # command
    from py2app.build_app import py2app as _py2app
    class py2app(_py2app):
        """py2app extensions to delete Qt debug libs."""
        # Add dmg option
        _py2app.user_options.append(
            ('no-dmg', None,
             'Do not build a dmg image from the bundle'),
        )
        _py2app.boolean_options.append('no-dmg')

        def initialize_options(self):
            _py2app.initialize_options(self)
            self.no_dmg = False

        def run(self):
            """Runs original py2app and deletes all files containing 
            'debug' in their name.
            """
            # First normal py2app run
            _py2app.run(self)

            # Then remove debuging files
            print '*** removing Qt debug libs ***'
            for root, dirs, files in os.walk(self.dist_dir):
                for file in files:
                    if 'debug' in file:
                        print 'removing', file
                        os.remove(os.path.join(root,file))

            # And run macdeployqt to copy plugins and build a dmg
            print '*** running macdeployqt ***'
            macdeploy_cmd = 'macdeployqt %s.app' % (self.get_appname())
            if self.no_dmg is False:
                macdeploy_cmd += ' -dmg'
            # The cd-ing is needed, since macdeploy with -dmg will name it 
            # as it's first argument and we don't like dmg names like 
            # dist/Hatta.app
            os.system('cd %s; ' % (self.dist_dir,) + macdeploy_cmd)
            
    config['cmdclass'] = {'py2app': py2app}
elif sys.platform == 'win32':
    ### Windows installer ###
	# Hack to make py2exe import win32com
	# http://www.py2exe.org/index.cgi/WinShell
    # ModuleFinder can't handle runtime changes to __path__, but win32com uses them
    import time
    try:
        # if this doesn't work, try import modulefinder
        import py2exe.mf as modulefinder
        import win32com
        for p in win32com.__path__[1:]:
            modulefinder.AddPackagePath("win32com", p)
        for extra in ["win32com.shell"]: #,"win32com.mapi"
            __import__(extra)
            m = sys.modules[extra]
            for p in m.__path__[1:]:
                modulefinder.AddPackagePath(extra, p)
    except ImportError:
        # no build path setup, no worries.
        pass
    import py2exe

    class InnoScript(object):
        def __init__(self, name, lib_dir, dist_dir, windows_exe_files = [],
                     lib_files = [], description = "", version = "1.0"):
            self.lib_dir = lib_dir
            self.dist_dir = dist_dir
            if not self.dist_dir[-1] in "\\/":
                self.dist_dir += "\\"
            self.name = name.capitalize()
            self.version = version
            self.description = description
            self.windows_exe_files = [self.chop(p) for p in windows_exe_files]
            self.lib_files = [self.chop(p) for p in lib_files
                if p.startswith(self.dist_dir)]

        def chop(self, pathname):
            return pathname[len(self.dist_dir):]

        def create(self, pathname="dist\\hatta.iss"):
            self.pathname = pathname
            ofi = self.file = open(pathname, "w")
            print >> ofi, "; WARNING: This script has been created by py2exe. Changes to this script"
            print >> ofi, "; will be overwritten the next time py2exe is run!"
            print >> ofi, r"[Setup]"
            print >> ofi, r"AppName=%s" % self.name
            print >> ofi, r"AppVerName=%s %s" % (self.name, self.version)
            print >> ofi, r"DefaultDirName={pf}\%s" % self.name
            print >> ofi, r"DefaultGroupName=%s" % self.name
            print >> ofi, r"InternalCompressLevel=ultra64"
            print >> ofi, r"VersionInfoVersion=%s" % '.'.join(self.version.split('.')[:2])
            print >> ofi, r"VersionInfoDescription=%s" % self.description
            print >> ofi, r"OutputBaseFilename=%s" % self.name + 'Setup'
            print >> ofi

            print >> ofi, r"[Files]"
            for path in self.windows_exe_files + self.lib_files:
                print >> ofi, r'Source: "%s"; DestDir: "{app}\%s"; Flags: ignoreversion' % (path, os.path.dirname(path))
            print >> ofi

            print >> ofi, r"[Icons]"
            for path in self.windows_exe_files:
                print >> ofi, r'Name: "{group}\%s"; Filename: "{app}\%s"' % \
                      (self.name, path)
            print >> ofi, r'Name: "{group}\Uninstall %s"; Filename: "{uninstallexe}"' % self.name
            print >> ofi

            print >> ofi, r"[UninstallDelete]"
            print >> ofi, r"Name: {app}; Type: filesandordirs"

        def compile(self):
            try:
                import ctypes
            except ImportError:
                try:
                    import win32api
                except ImportError:
                    import os
                    os.startfile(self.pathname)
                else:
                    print "Ok, using win32api."
                    win32api.ShellExecute(0, "compile", self.pathname, None, None, 0)
            else:
                print "Cool, you have ctypes installed."
                res = ctypes.windll.shell32.ShellExecuteA(0, "compile", self.pathname, None, None, 0)
                if res < 32:
                    raise RuntimeError, "ShellExecute failed, error %d" % res
    # class InnnoScript

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
            version = hatta.__version__
            if version.endswith('dev'):
                from datetime import datetime
                version = version[:-3] + '.' + datetime.now().strftime('%Y%m%d%H%M')
                
            # create the Installer, using the files py2exe has created.
            script = InnoScript("hatta", lib_dir, dist_dir,
                                self.console_exe_files+self.windows_exe_files,
                                self.lib_files,
                                hatta.description, version)
            print "*** creating the inno setup script***"
            script.create(os.path.join(self.dist_dir, hatta.name + '.iss'))
            print "*** compiling the inno setup script***"
            script.compile()
            # Note: By default the final setup.exe will be in an
            # Output subdirectory.
    # class BuildInstaller
    
	config['zipfile'] = None
    config['cmdclass'] = {"py2exe": BuildInstaller}
    config['windows'] = [{
		'script': 'hatta_qticon.py',
        'icon_resources': [(1, "resources/hatta.ico")],
    }]
    
    # Adding MS runtime C libraries
    if sys.version.startswith('2.6'):
        from win32com.shell import shellcon, shell
        from glob import glob
        windir = shell.SHGetFolderPath(0, shellcon.CSIDL_WINDOWS, 0, 0)
        dlldir = glob(os.path.join(windir, u'WinSxS', '*Microsoft.VC90.CRT*'))[0]
        dlls = glob(os.path.join(dlldir, '*.dll'))
        dest_dir = 'Microsoft.VC90.CRT'
        from tempfile import gettempdir
        from shutil import copy
        manifest = os.path.join(gettempdir(), 'Microsoft.VC90.CRT.manifest')
        copy(glob(os.path.join(
                windir, 'WinSxS', 'Manifests', '*VC90.CRT*manifest'))[0],
            manifest)
        config['data_files'].extend([
            (dest_dir, glob(os.path.join(dlldir, '*.dll'))),
            (dest_dir, [manifest]),
        ])
    else:
        # For Python < 2.6 we don't need separate dir,
        # so let's leave the work to py2app
        origIsSystemDLL = py2exe.build_exe.isSystemDLL
        def isSystemDLL(pathname):
            if 'msvc' in os.path.basename(pathname).lower():
                return 0
            elif 'dwmapi' in os.path.basename(pathname).lower():
                return 0
            return origIsSystemDLL(pathname)
        py2exe.build_exe.isSystemDLL = isSystemDLL    

else: # Other UNIX-like
    config['scripts'] = ['hatta_qticon.py', 'hatta_gtkicon.py']

if __name__=='__main__':
    setup(**config)
    try:
        import pybonjour
    except ImportError:
        print u'*** Warning ***'
        print u'Please install pybonjour to build a full-featured binary.'
