#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Implements a cross-platform system tray icon for a better desktop 
experience with Hatta. Allows to start, stop and interact with the wiki 
without command line knowledge.

Uses Qt and PyQt in particular for this task.
"""

from os.path import join
import gettext
import signal
from subprocess import Popen
import sys
from urllib import urlopen
import webbrowser

from PyQt4.QtGui import QApplication, QSystemTrayIcon, QMenu, QIcon
from PyQt4.QtCore import QString

from hatta import WikiConfig

class HattaTrayIcon(QSystemTrayIcon):
    """Extension of QSystemTrayIcon for customization towards Hatta."""
    def __init__(self, config):
        """Initialize connection data and status menu GUI."""
        super(HattaTrayIcon, self).__init__()
        # Global wiki settings
        host = config.get('interface')
        port = int(config.get('port'))
        self.url = 'http://%s:%d/' % (host, port)

        # Setup try icon
        self.setIcon(QIcon(join(
            sys.prefix, 'share/icons/hicolor/32x32/hatta.png')))
        self.setContextMenu(self.__create_menu())
        self.setToolTip(QString(_(u'Hatta Wiki menu')))
        self.show()

        # Start wiki subprocess
        self.wiki_process_pid = Popen([sys.executable,
            'hatta.py']).pid

        self.showMessage(QString(_(u'Welcome to Hatta Wiki')),
                QString(_(u'Click the hat icon to start or quit the '
                u'Hatta Wiki.'))
        )

    def __create_menu(self):
        """Creates and populates the context menu."""
        self.menu = QMenu(QString(_(u'Hatta Wiki menu')))
        self.menu.addAction(QString(_(u'Open Hatta')), self.on_wiki_open)
        self.menu.addAction(QString(_(u'Quit Hatta')), self.on_wiki_quit)

        return self.menu

    def on_wiki_open(self):
        """Callback for opening wiki page in a browser."""
        webbrowser.open(self.url)

    def on_wiki_quit(self):
        """Callback to close running Hatta instance and unload statu 
        icon."""
        urlopen('http://localhost:%s/off-with-his-head'
                    % int(config.get('port'))).read(1)
        self.menu.destroy()
        global app
        app.quit()

config = WikiConfig(
    # Here you can modify the configuration: uncomment and change
    # the ones you need. Note that it's better use environment
    # variables or command line switches.

    interface='localhost',
    port=8080
    # pages_path = 'docs'
    # cache_path = 'cache'
    # front_page = 'Home'
    # site_name = 'Hatta Wiki'
    # page_charset = 'UTF-8'
)
if __name__ == '__main__':
    try:
        global _
        _ = gettext.translation('hatta', fallback=True).ugettext

        app = QApplication(sys.argv)
        QApplication.setQuitOnLastWindowClosed(False)
        status_icon = HattaTrayIcon(config)
        app.exec_()
            
    except KeyboardInterrupt:
        pass

