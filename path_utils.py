import sys
import os


class Error(Exception):
    pass

def user_data_dir(appname, owner=None, version=None):
    """Return full path to the user-specific data dir for this application.
    
        "appname" is the name of application.
        "owner" (only required and used on Windows) is the name of the
            owner or distributing body for this application. Typically
            it is the owning company name.
        "version" is an optional version path element to append to the
            path. You might want to use this if you want multiple versions
            of your app to be able to run independently. If used, this
            would typically be "<major>.<minor>".
    
    Typical user data directories are:
        Windows:    C:\Documents and Settings\USER\Application Data\<owner>\<appname>
        Mac OS X:   ~/Library/Application Support/<appname>
        Unix:       ~/.local/share/<appname>
    """
    if sys.platform.startswith("win"):
        # Try to make this a unicode path because SHGetFolderPath does
        # not return unicode strings when there is unicode data in the
        # path.
        if owner is None:
            raise Error("must specify 'owner' on Windows")
        from win32com.shell import shellcon, shell
        path = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)
        try:
            path = unicode(path)
        except UnicodeError:
            pass
        path = os.path.join(path, owner, appname)
    elif sys.platform == 'darwin':
        from Carbon import Folder, Folders
        path = Folder.FSFindFolder(Folders.kUserDomain,
                                   Folders.kApplicationSupportFolderType,
                                   Folders.kDontCreateFolder)
        path = os.path.join(path.FSRefMakePath(), appname)
    else:
        from xdg.BaseDirectory import xdg_data_home
        path = os.path.join(xdg_data_home, appname)
    if version:
        path = os.path.join(path, version)
    return path


def site_data_dir(appname, owner=None, version=None):
    """Return full path to the user-shared data dir for this application.
    
        "appname" is the name of application.
        "owner" (only required and used on Windows) is the name of the
            owner or distributing body for this application. Typically
            it is the owning company name.
        "version" is an optional version path element to append to the
            path. You might want to use this if you want multiple versions
            of your app to be able to run independently. If used, this
            would typically be "<major>.<minor>".
    
    Typical user data directories are:
        Windows:    C:\Documents and Settings\All Users\Application Data\<owner>\<appname>
        Mac OS X:   /Library/Application Support/<appname>
        Unix:       /etc/<lowercased-appname>
    """
    if sys.platform.startswith("win"):
        # Try to make this a unicode path because SHGetFolderPath does
        # not return unicode strings when there is unicode data in the
        # path.
        if owner is None:
            raise Error("must specify 'owner' on Windows")
        from win32com.shell import shellcon, shell
        shellcon.CSIDL_COMMON_APPDATA = 0x23 # missing from shellcon
        path = shell.SHGetFolderPath(0, shellcon.CSIDL_COMMON_APPDATA, 0, 0)
        try:
            path = unicode(path)
        except UnicodeError:
            pass
        path = os.path.join(path, owner, appname)
    elif sys.platform == 'darwin':
        from Carbon import Folder, Folders
        path = Folder.FSFindFolder(Folders.kLocalDomain,
                                   Folders.kApplicationSupportFolderType,
                                   Folders.kDontCreateFolder)
        path = os.path.join(path.FSRefMakePath(), appname)
    else:
        path = "/etc/"+appname.lower()
    if version:
        path = os.path.join(path, version)
    return path

def user_cache_dir(appname, owner=None):
    """Return full path to the user-shared cache dir for this application.
    
        "appname" is the name of application.
        "owner" (only required and used on Windows) is the name of the
            owner or distributing body for this application. Typically
            it is the owning company name.
    
    Typical user data directories are:
        Windows:    C:\Documents and Settings\USER\Application Data\<owner>\<appname>\cache
        Mac OS X:   ~/Library/Caches/<appname>
        Unix:       ~/.cache/<appname>
    """
    if sys.platform.startswith("win"):
        # Try to make this a unicode path because SHGetFolderPath does
        # not return unicode strings when there is unicode data in the
        # path.
        if owner is None:
            raise Error("must specify 'owner' on Windows")
        from win32com.shell import shellcon, shell
        shellcon.CSIDL_COMMON_APPDATA = 0x23 # missing from shellcon
        path = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)
        try:
            path = unicode(path)
        except UnicodeError:
            pass
        path = os.path.join(path, owner, appname, u'cache')
    elif sys.platform == 'darwin':
        from Carbon import Folder, Folders
        path = Folder.FSFindFolder(Folders.kUserDomain,
                                   Folders.kCachedDataFolderType,
                                   Folders.kDontCreateFolder)
        path = os.path.join(path.FSRefMakePath(), appname)
    else:
        from xdg.BaseDirectory import xdg_cache_home
        path = os.path.join(xdg_cache_home, appname)
    return path

def user_config_file(appname, owner=None, filename=None):
    """Return full path to the user-shared application main config file.
    
        "appname" is the name of the application.
        "filename" is the name of the configuration file. The default is 
            <application>.conf.
        "owner" (only required and used on Windows) is the name of the
            owner or distributing body for this application. Typically
            it is the owning company name.
    
    Typical user data directories are:
        Windows:    C:\Documents and Settings\USER\Application Data\<owner>\<appname>\<appname>.conf
        Mac OS X:   ~/Library/Preferences/<appname>.conf
        Unix:       ~/.cache/<appname>
    """
    if filename is None:
        filename = u'.'.join([appname, u'conf'])
    if sys.platform.startswith("win"):
        # Try to make this a unicode path because SHGetFolderPath does
        # not return unicode strings when there is unicode data in the
        # path.
        if owner is None:
            raise Error("must specify 'owner' on Windows")
        from win32com.shell import shellcon, shell
        shellcon.CSIDL_COMMON_APPDATA = 0x23 # missing from shellcon
        path = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)
        try:
            path = unicode(path)
        except UnicodeError:
            pass
        path = os.path.join(path, owner, appname, filename)
    elif sys.platform == 'darwin':
        from Carbon import Folder, Folders
        path = Folder.FSFindFolder(Folders.kUserDomain,
                                   Folders.kPreferencesFolderType,
                                   Folders.kDontCreateFolder)
        path = os.path.join(path.FSRefMakePath(), filename)
    else:
        from xdg.BaseDirectory import xdg_config_home
        path = os.path.join(xdg_config_home, appname, filename)
    return path

if __name__ == "__main__":
    print "applib: user data dir:", user_data_dir("Komodo", "ActiveState")
    print "applib: site data dir:", site_data_dir("Komodo", "ActiveState")
    print "applib: user cache dir:", user_cache_dir("Komodo",
                                                    "ActiveState")
    print "applib: user config file:", user_config_file("Komodo",
                                                        "ActiveState")

