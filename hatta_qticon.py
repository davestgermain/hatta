#!/usr/bin/env python

# -*- coding: utf-8 -*-

"""
Implements a cross-platform system tray icon for a better desktop 
experience with Hatta. Allows to start, stop and interact with the wiki 
without command line knowledge.

Uses Qt and PyQt in particular for this task.
"""

from os.path import join
from select import select
from thread import start_new_thread
from time import sleep
from traceback import format_exc
from urllib import urlopen, quote
from wsgiref import simple_server
import gettext
import os
try:
    import pybonjour
except: # Deliberately so, since pybonjour is bundled, but bonjour 
        # itself isn't there always
    pybonjour = None
import sys
import webbrowser

from PyQt4.QtGui import (QApplication, QSystemTrayIcon, QMenu, QIcon,
    QMessageBox, QAction, QKeySequence, QWidget, QVBoxLayout, QGridLayout,
    QLabel, QSpinBox, QToolTip, QLineEdit, QHBoxLayout, QPushButton,
    QFileDialog, QPixmap, QCheckBox, QDesktopServices, QDialog)
from PyQt4.QtCore import (QString, QThread, pyqtSignal, pyqtSlot, Qt,
    QPoint, QLocale)

from hatta import WikiConfig, Wiki, WikiRequest, project_name, project_url

from error_dialog import ErrorDialog

def module_path():
    """ This will get us the program's directory,
    even if we are frozen using py2exe"""

    if we_are_frozen():
        return os.path.dirname(unicode(
            sys.executable, sys.getfilesystemencoding()))

    return os.path.dirname(unicode(__file__, sys.getfilesystemencoding()))


def we_are_frozen():
    """Returns whether we are frozen via py2exe.
    This will affect how we find out where we are located."""

    return hasattr(sys, "frozen") and sys.frozen == "windows_exe"

class HattaThread(QThread):
    """
    An instance of wiki server running in the background and handling incoming 
    requests.
    """

    # For passing multithread exception in Qt.
    exception_signal = pyqtSignal(str)

    def __init__(self, config, error_handler):
        """Create a wiki instance and a server for it."""
        super(HattaThread, self).__init__()
        self.config = config
        self.wiki = Wiki(config)
        self.server = simple_server.make_server(
                config.get('interface', ''),
                int(config.get('port', 8080)),
                self.application_wrapper)

        self.exception_signal.connect(error_handler)

    def run(self):
        """Thread execution. Handles requests."""
        while not self.wiki.dead:
            self.server.handle_request()

    def application_wrapper(self, *args, **kwargs):
        try:
            return self.wiki.application(*args, **kwargs)
        except Exception as e:
            self.exception_signal.emit(unicode(e))
            # It's very important to shut down the thread, so that the threaded 
            # werkzeug won't continue to run and send other exceptions.
            self.quit()

    def quit(self):
        self.wiki.daed = True
        urlopen('http://localhost:%s/off-with-his-head' %
                self.config.get('port')).close()
        self.server.server_close()
        super(HattaThread, self).quit()

class ZeroconfThread(QThread):
    """Handles wiki registration and searches for other wikis.

    A separate thread, as the pybonjour lib is polling."""

    new_services = pyqtSignal(set)
    timeout = 5 # seconds

    def register_callback(self, sdRef, flags, error_code, name, regtype,
                          domain):
        """Called when a response to Zeroconf register is given."""
        if error_code != pybonjour.kDNSServiceErr_NoError:
            # TODO: Should give some error
            pass

    def browse_callback(self, sdRef, flags, interface_index, error_code,
                        service_name, reg_type, reply_domain):
        """Called when a Zeroconf response for browsing is given."""
        if error_code != pybonjour.kDNSServiceErr_NoError:
            return

        def resolve_callback(sdRef, flags, interface_index,
                             error_code, full_name, host_target,
                             port, txt_record):
            """Called when a service name and data has been resolved.

            Needs to be embedded so that non-escaped service name can be 
            used.
            """
            if error_code != pybonjour.kDNSServiceErr_NoError:
                return
            self.resolved.append((
                service_name,
                host_target,
                port))

        self.resolve_sdRef = pybonjour.DNSServiceResolve(
            interfaceIndex=interface_index,
            name=service_name,
            regtype=reg_type,
            domain=reply_domain,
            callBack=resolve_callback)
        # Add timeout capability
        try:
            ready = select([self.resolve_sdRef], [], [], self.timeout)
            if self.resolve_sdRef in ready[0]:
                pybonjour.DNSServiceProcessResult(self.resolve_sdRef)
                if flags & pybonjour.kDNSServiceFlagsAdd:
                    self.services.add(self.resolved.pop())
                else:
                    try:
                        self.services.remove(self.resolved.pop())
                    except KeyError:
                        pass
            if not flags & pybonjour.kDNSServiceFlagsMoreComing:
                self.new_services.emit(list(self.services))
        finally:
            self.resolve_sdRef.close()

    def __init__(self, config, services_handler):
        super(ZeroconfThread, self).__init__()
        self.name = config.get('site_name')
        self.reg_type = (u'_http._tcp')
        self.port = int(config.get('port', 8080))

        self.resolved = []
        self.services = set()

        self.new_services.connect(services_handler)

    def run(self):
        self.browse_sdRef = pybonjour.DNSServiceBrowse(
            regtype=self.reg_type,
            callBack=self.browse_callback)
        try:
            while True:
                ready = select([self.browse_sdRef], [], [], self.timeout)
                if self.browse_sdRef in ready[0]:
                    pybonjour.DNSServiceProcessResult(self.browse_sdRef)
        finally:
            self.browse_sdRef.close()

    def register_wiki(self):
        # Register Hatta instance
        self.service_ref = pybonjour.DNSServiceRegister(
            flags=pybonjour.kDNSServiceFlagsNoAutoRename,
            name=self.name,
            regtype=self.reg_type,
            port=self.port,
            callBack=self.register_callback)

        ready = select([self.service_ref], [], [], self.timeout)
        if self.service_ref in ready[0]:
            pybonjour.DNSServiceProcessResult(self.service_ref)

    def quit(self):
        """Close Zeroconf service connection."""
        # This is needed, as closing service_ref would emit this
        # signal.
        self.new_services.disconnect()
        try:
            self.service_ref.close()
        except AttributeError:
            pass
        super(ZeroconfThread, self).quit()

class HattaTrayIcon(QSystemTrayIcon):
    """Extension of QSystemTrayIcon for customization towards Hatta."""
    config_filename = join(
        str(QDesktopServices.storageLocation(
            QDesktopServices.DataLocation)),
        project_name,
        project_name + u'.conf')
    dist_icon = os.path.join(module_path(),
                             'share/icons/hicolor/64x64/hatta.png')
    debug_icon = os.path.join(module_path(), 'resources/hatta.png')

    def save_config(self):
        """Saves a WikiConfig instance with custom data."""
        config_dir = os.path.dirname(self.config_filename)
        try:
            os.makedirs(config_dir)
        except OSError, e:
            if not os.path.isdir(config_dir):
                raise e
        self.config.save_config(self.config_filename)

    @pyqtSlot(unicode, unicode, int, bool)
    def reload_config(self, site_name, pages_path, port, announce):
        """Change own config and realod the wiki."""
        self.setDisabled(True)
        self.menu.clear()
        self.menu.addAction(_(u'Restarting wiki...'))

        self.wiki_thread.quit()
        if self.zeroconf_thread is not None:
            self.zeroconf_thread.quit()
            # Necessary if turned off/on via preferences
            self.zeroconf_thread = None

        self._modify_url(port)
        self.config.set('site_name', str(site_name))
        self.config.set('pages_path', str(pages_path))
        self.config.set('port', port)
        self.should_announce = announce
        self.config.set('announce', str(announce))
        self.save_config()

        self.wiki_thread = HattaThread(self.config, self.on_error)
        self.wiki_thread.start()

        if pybonjour is not None:
            def delay_zeroconf_start():
                # This sleep is needed, as mdns server needs to change the 
                # port on which wiki is registered.
                # TODO: This is hidious --- make some kind of wait maybe?
                sleep(1)
                self.zeroconf_thread = ZeroconfThread(
                    self.config,
                    self.on_new_services)
                self.zeroconf_thread.start()
                self.register_wiki()

            start_new_thread(delay_zeroconf_start, ())

        # Unfreeze GUI
        self.on_new_services([])

    def setDisabled(self, disabled=True):
        """Change tray icon to between disabled or normal state."""
        self.menu.setDisabled(disabled)
        self.setIcon(QIcon(self.hatta_icon.pixmap(64, 64,
            QIcon.Disabled if disabled else QIcon.Normal)))

    def __init__(self):
        """Initialize connection data and status menu GUI."""
        super(HattaTrayIcon, self).__init__()
        # First setup tray icon and display inform user about starting
        self.hatta_icon = QIcon(QPixmap(
            self.dist_icon if os.path.isfile(self.dist_icon) else
            self.debug_icon))
        self.menu = QMenu(QString(_(u'Hatta Wiki menu')))
        self.setDisabled(True)

        self.menu.addAction(_(u'Starting wiki...'))
        self.setContextMenu(self.menu)
        self.setToolTip(QString(_(u'Click this icon to interact with'
                                  u' Hatta wiki.')))

        self.show()

        # Get config from file or create
        self.config = WikiConfig()
        self.config.parse_files([self.config_filename])
        if len(self.config.config) == 0:
            self.config = default_config
            self.save_config()
        self.config.parse_args()

        # Global wiki settings
        port = int(self.config.get('port'))
        self._modify_url(port)
        self.should_announce = bool(self.config.get_bool('announce', 1))

        self.preferences_window = PreferenceWindow(self, self.hatta_icon,
                                                   self.config)
        self.preferences_window.config_change.connect(
            self.reload_config,
            type=Qt.QueuedConnection)

        self.default_actions = []
        self.discovery_header = QAction(_(u'Nearby wikis:'), self)
        self.discovery_header.setToolTip(_(
            'Displays a list of nearby discovered wikis. '
            u'Click one to view it.'))
        self.discovery_header.setDisabled(True)

        # Start wiki thread
        self.wiki_thread = HattaThread(self.config, self.on_error)
        self.wiki_thread.start()

        self.showMessage(QString(_(u'Welcome to Hatta Wiki')),
                QString(_(u'Click the hat icon to start or quit the '
                u'Hatta Wiki.'))
        )

        self._prepare_default_menu()
        self.menu.addActions(self.default_actions)

        # Start Zeroconf thread
        if pybonjour:
            self.zeroconf_thread = ZeroconfThread(self.config,
                                                  self.on_new_services)
            self.zeroconf_thread.start()
            self.register_wiki()
        else:
            self.zeroconf_thread = None

        # Unfreeze the GUI
        self.on_new_services([])

    def register_wiki(self):
        """Tells Zeroconf thread to register wiki in Bonjour if 
        appropriate."""
        if (pybonjour is not None and self.should_announce and
            self.zeroconf_thread is not None):
            self.zeroconf_thread.register_wiki()

    def _prepare_default_menu(self):
        """Creates and populates the context menu."""
        action = QAction(_(u'&Preferences'), self)
        action.setToolTip(_(u'Lets you configure the wiki.'))
        action.setShortcut(QKeySequence.Preferences)
        action.triggered.connect(self.preferences_window.show)
        self.default_actions.append(action)
        action = QAction(_(u'&Open wiki'), self)
        action.setShortcuts(QKeySequence.Open)
        action.setToolTip(_(u'Opens the wiki in the default browser.'))
        action.triggered.connect(self.on_wiki_open)
        self.default_actions.append(action)
        action = QAction(QString(_(u'&Quit')), self)
        action.setShortcut(Qt.CTRL + Qt.Key_Q)
        action.setToolTip(_(u'Stops the wiki and quits the'
                              u' status icon.'))
        action.triggered.connect(self.on_wiki_quit)
        self.default_actions.append(action)

    def _modify_url(self, port):
        """Modifies port in URL."""
        self.url = 'http://localhost:%d/' % (port,)

    def on_wiki_open(self):
        """Callback for opening wiki page in a browser."""
        webbrowser.open(self.url)

    def on_wiki_quit(self):
        """Callback to close running Hatta instance and unload statu 
        icon."""
        # Hide the icon first, so the user won't try to click anything in 
        # a strange long quitting scenario.
        self.hide()
        self.wiki_thread.quit()
        if self.zeroconf_thread is not None:
            self.zeroconf_thread.quit()
        self.menu.destroy()
        self.save_config()
        global app
        app.quit()

    pyqtSlot(str)
    def on_error(self, strerror):
        """Displays error and send bug request."""
        report_bug('bugs@hatta-wiki.org', strerror)

    def _make_discovery_action(self, name, host, port):
        """Creates a menu action from a discovered wiki."""
        action = QAction(_(u'    %(wiki_name)s on %(host_name)s') % dict(
            wiki_name=name, host_name=host), self)
        action.setToolTip(_(u'Opens %(wiki_name)s in browser.') 
                          % dict(wiki_name=name))
        action.triggered.connect((lambda x, y: lambda: webbrowser.open(
                'http://%s:%d' % (x, y)))(host, port))
        return action

    pyqtSlot(set)
    def on_new_services(self, services):
        """Displays discovered services in menu."""
        self.menu.clear()

        if len(services) > 0:
            # Apparently Zeroconf daemon works and returns results
            self.menu.addAction(self.discovery_header)

            for name, host, port in services[:4]:
                self.menu.addAction(self._make_discovery_action(name, host,
                                                                port))
            if len(services) > 4:
                submenu = self.menu.addMenu('    ' + _(u'More wikis'))
                submenu.setToolTip(_(
                    u'Shows even more wikis discovered nearby!'))
                for name, host, port in services[5:]:
                    submenu.addAction(self._make_discovery_action(name, host,
                                                                  port))
            self.menu.addSeparator()
        elif len(services) == 0 and pybonjour is None:
            # Seems Zeroconf returned no results. Probably no bonjour 
            # installed.
            self.menu.addAction(self.discovery_header)

            if sys.platform.startswith('win32'):
                info = QAction(_(
                    u'    Install Bonjour to view nearby wikis'),
                    self)
                info.triggered.connect((lambda: lambda:
                        webbrowser.open('http://support.apple.com/'
                                        'downloads/Bonjour_for_Windows'))())
            else:
                info = QAction(_(
                    u'    Install libavahi-compat-libdnssd1'
                    u' to view nearby wikis'),
                    self
                )
                info.setDisabled(True)
            self.menu.addAction(info)

        self.menu.addActions(self.default_actions)
        self.setDisabled(False)
        self.refresh_menu()

    def refresh_menu(self):
        """Forces Qt to process events."""
        self.menu.repaint()
        global app
        if app.hasPendingEvents():
            app.processEvents()

default_config = WikiConfig(
    # Here you can modify the configuration: uncomment and change
    # the ones you need. Note that it's better use environment
    # variables or command line switches.

    interface='',
    port=8080,
    site_name='Hatta Wiki',
    pages_path=join(
        str(QDesktopServices.storageLocation(
            QDesktopServices.DataLocation)),
        project_name,
        u'pages'),
    cache_path=join(
        str(QDesktopServices.storageLocation(
            QDesktopServices.CacheLocation)),
        project_name),
    # front_page = 'Home'
    # page_charset = 'UTF-8'
)

class PreferenceWindow(QWidget):
    """Panel with most important preferences editable to user."""

    config_change = pyqtSignal(unicode, unicode, int, bool)

    def __init__(self, parent, icon, config):
        super(PreferenceWindow, self).__init__(
            None,
            Qt.Window | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint
            | Qt.WindowTitleHint)

        self.setWindowIcon(icon)

        # Preferences data
        self.wiki_name = config.get('site_name',
                                    _(u'Enter the name of your wiki'))
        self.wiki_page_path = config.get('pages_path',
                                         _(u'Choose path for wiki pages'))
        self.wiki_port = int(config.get('port', 8080))
        self.should_announce = bool(config.get_bool('announce', 1))
        # Set up GUI code
        self.setWindowTitle(_(u'Hatta preferences'))
        self.setWindowModality(Qt.WindowModal)

        self.main_vbox = QVBoxLayout(self)
        grid_layout = QGridLayout()
        # Wiki name input
        tooltip = _(u'Sets the name of you wiki. The name will be visible '
                   u'across the wiki and on discovery.')
        self.name_label = QLabel(_(u'Wiki name:'), self)
        self.name_label.setToolTip(tooltip)
        self.name_edit = QLineEdit(self.wiki_name, self)
        self.name_edit.setToolTip(tooltip)
        grid_layout.addWidget(self.name_label, 0, 0)
        grid_layout.addWidget(self.name_edit, 0, 1)

        # Pages dir choosing
        tooltip = _(u'Sets the pages directory, where wiki pages will be '
                   u'held.')
        self.pages_label = QLabel(_(u'Pages path:'), self)
        self.pages_label.setToolTip(tooltip)
        pages_layout = QHBoxLayout()
        self.pages_edit = QLineEdit(self.wiki_page_path, self)
        self.pages_edit.setToolTip(tooltip)
        self.pages_chooser = QPushButton(_(u'&Open...'), self)
        self.pages_chooser.clicked.connect(self.choose_page_dir)
        self.pages_chooser.setToolTip(tooltip)
        pages_layout.addWidget(self.pages_edit)
        pages_layout.addWidget(self.pages_chooser)
        grid_layout.addWidget(self.pages_label, 1, 0)
        grid_layout.addLayout(pages_layout, 1, 1)

        # Listen port selection port
        min_port = 1
        max_port = 65535
        tooltip = _(u'Sets the port on which wiki is listening on.'
                    u' Valid ports: %(min_port)d to %(max_port)d.'
                   ) % dict(min_port=min_port, max_port=max_port)
        self.port_label = QLabel(_(u'Listen port:'))
        self.port_label.setToolTip(tooltip)
        self.port_spin = QSpinBox(self)
        self.port_spin.setRange(min_port, max_port)
        self.port_spin.setValue(self.wiki_port)
        self.port_spin.setToolTip(tooltip)
        grid_layout.addWidget(self.port_label, 2, 0)
        grid_layout.addWidget(self.port_spin, 2, 1)

        # Announcement switch
        tooltip = _(u'Should wiki announce itself to the neighbourhood'
                    u' network?')
        self.announce_checkbox = QCheckBox(_(u'Announce hatta'))
        self.announce_checkbox.setToolTip(tooltip)
        self.announce_checkbox.setChecked(self.should_announce)
        if pybonjour is None:
            self.announce_checkbox.setVisible(False)
        grid_layout.addWidget(self.announce_checkbox, 3, 1)

        self.main_vbox.addLayout(grid_layout)

        # File choosing dialog for pages path
        self.page_dir_dialog = QFileDialog(self,
                                           _(u'Choose page directory'))
        self.page_dir_dialog.setAcceptMode(QFileDialog.AcceptOpen)
        self.page_dir_dialog.setFileMode(QFileDialog.Directory)
        self.page_dir_dialog.setOption(QFileDialog.ShowDirsOnly, True)
        self.page_dir_dialog.setDirectory(config.get('pages_path'))

    def choose_page_dir(self, clicked):
        """Shows a directory choosing dialog and updates preferences text 
        field."""
        def set_pages_dir():
            self.pages_edit.setText(
                self.page_dir_dialog.directory().absolutePath())
        self.page_dir_dialog.open(set_pages_dir)

    def closeEvent(self, event):
        """Notify config change to main app."""
        self.hide()
        self.wiki_name = self.name_edit.text()
        self.wiki_page_path = self.pages_edit.text()
        self.wiki_port = self.port_spin.value
        self.should_announce = self.announce_checkbox.isChecked()
        self.config_change.emit(
            unicode(self.name_edit.text()),
            unicode(self.pages_edit.text()),
            int(self.port_spin.value()),
            bool(self.should_announce))


error_dialog = None
def report_bug(email, caption):
    error_dialog.prepare_error(unicode(caption), format_exc())
    if error_dialog.exec_() == QDialog.Accepted:
        link = 'mailto:%s?subject=%s&body=%s' % (
            email,
            quote(u'[Bug] ' + unicode(caption)),
            quote(error_dialog.get_bug_dump()))
        webbrowser.open(link)
    #QApplication.exit()

if __name__ == '__main__':
    try:
        from locale import getlocale, getdefaultlocale, setlocale, LC_ALL
        setlocale(LC_ALL, '')
        lang = str(QLocale.system().name()).split('_')[0]

        localedir = os.path.join(module_path(), 'locale')
        if not os.path.isdir(localedir):
            # Already installed
            localedir = os.path.join(module_path(), 'share', 'locale')
        translation = gettext.translation('hatta', localedir,
                languages=[lang], fallback=True)
        translation.install(unicode=1)

        try:
            app = QApplication(sys.argv)
            QApplication.setQuitOnLastWindowClosed(False)
            error_dialog = ErrorDialog(module_path())
            status_icon = HattaTrayIcon()
            app.exec_()
        except Exception as e:
            report_bug('dhubleizh@o2.pl', unicode(e))
    except KeyboardInterrupt:
        pass

