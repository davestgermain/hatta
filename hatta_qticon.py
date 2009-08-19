#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Implements a cross-platform system tray icon for a better desktop 
experience with Hatta. Allows to start, stop and interact with the wiki 
without command line knowledge.

Uses Qt and PyQt in particular for this task.
"""

from os.path import join
from thread import start_new_thread
from time import sleep
from urllib import urlopen, unquote
from wsgiref import simple_server
import gettext
try:
    import pybonjour
except ImportError:
    pybonjour = None
import sys
import webbrowser

from PyQt4.QtGui import (QApplication, QSystemTrayIcon, QMenu, QIcon,
    QMessageBox, QAction, QKeySequence, QWidget, QVBoxLayout, QGridLayout,
    QLabel, QSpinBox, QToolTip, QLineEdit, QHBoxLayout, QPushButton,
    QFileDialog)
from PyQt4.QtCore import (QString, QThread, pyqtSignal, pyqtSlot, Qt,
    QPoint)

from hatta import WikiConfig, Wiki, WikiRequest, name, organization, url
from path_utils import user_data_dir, user_cache_dir, user_config_file

class HattaThread(QThread):
    """
    An instance of wiki server running in the background and handling incoming 
    requests.
    """

    # For passing multithread exception in Qt.
    exception_signal = pyqtSignal(Exception)

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
        except Exception, e:
            self.exception_signal.emit(e)

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

    def register_callback(self, sdRef, flags, error_code, name, regtype,
                          domain):
        """Called when a response to Zeroconf register is given.

        Exits the thread if something went wrong. This means no more 
        resources won't be wasted and no Zeroconf info will be passed to 
        the tray icon This means no more resources won't be wasted and no 
        Zeroconf info will be passed to the tray icon."""
        if error_code != pybonjour.kDNSServiceErr_NoError:
            self.quit()

        self.main_loop()

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

        resolve_sdRef = pybonjour.DNSServiceResolve(
            interfaceIndex=interface_index,
            name=service_name,
            regtype=reg_type,
            domain=reply_domain,
            callBack=resolve_callback)
        # Add timeout capability
        try:
            pybonjour.DNSServiceProcessResult(resolve_sdRef)
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
            resolve_sdRef.close()

    def __init__(self, config, services_handler):
        super(ZeroconfThread, self).__init__()
        self.name = config.get('site_name')
        self.reg_type = (u'_http._tcp')
        self.port = int(config.get('port', 8080))

        self.resolved = []
        self.services = set()

        self.new_services.connect(services_handler)

    def run(self):
        # Register Hatta instance
        self.service_ref = pybonjour.DNSServiceRegister(
            flags=pybonjour.kDNSServiceFlagsNoAutoRename,
            name=self.name,
            regtype=self.reg_type,
            port=self.port,
            callBack=self.register_callback)
        try:
            pybonjour.DNSServiceProcessResult(self.service_ref)
            self.main_loop()
        finally:
            self.service_ref.close()

    def main_loop(self):
        self.browse_sdRef = pybonjour.DNSServiceBrowse(
            regtype=self.reg_type,
            callBack=self.browse_callback)
        try:
            while True:
                pybonjour.DNSServiceProcessResult(self.browse_sdRef)
        finally:
            self.browse_sdRef.close()

    def quit(self):
        """Close Zeroconf service connection."""
        # This is needed, as closing service_ref would emit this
        # signal.
        self.new_services.disconnect()
        self.service_ref.close()
        super(ZeroconfThread, self).quit()

class HattaTrayIcon(QSystemTrayIcon):
    """Extension of QSystemTrayIcon for customization towards Hatta."""

    config_filename = user_config_file(
        name,
        organization)

    def save_config(self):
        """Saves a WikiConfig instance with custom data."""
        self.config.save_config(self.config_filename)

    @pyqtSlot(unicode, unicode, int)
    def reload_config(self, site_name, pages_path, port):
        """Change own config and realod the wiki."""
        self.menu.setDisabled(True)
        self.menu.clear()
        self.menu.addAction(_(u'Restarting wiki...'))

        self.wiki_thread.quit()
        if self.zeroconf_thread is not None:
            self.zeroconf_thread.quit()

        self.url = 'http://%s:%d/' % ('', port)
        self.config.set('site_name', str(site_name))
        self.config.set('pages_path', str(pages_path))
        self.config.set('port', port)
        self.save_config()

        self.wiki_thread = HattaThread(self.config, self.on_error)
        self.wiki_thread.start()

        if self.zeroconf_thread is not None:
            def delay_zeroconf_start():
                # This sleep is needed, as mdns server needs to change the 
                # port on which wiki is registered.
                # TODO: This is hidious --- make some kind of wait maybe?
                sleep(1)
                self.zeroconf_thread = ZeroconfThread(
                    self.config,
                    self.on_new_services)
                self.zeroconf_thread.start()

            start_new_thread(delay_zeroconf_start, ())
        else:
            # Partial solution to race condition: only have a menu when 
            # there's no zeroconf thread. If it's present, somehow the 
            # preferences window doens't show until thread gives browsed 
            # entries.
            self.on_new_services([])

    def __init__(self):
        """Initialize connection data and status menu GUI."""
        super(HattaTrayIcon, self).__init__()
        # First setup tray icon and display inform user about starting
        self.menu = QMenu(QString(_(u'Hatta Wiki menu')))
        self.menu.setDisabled(True)
        self.menu.addAction(_(u'Starting wiki...'))
        self.setIcon(QIcon(join(
            sys.prefix, 'share/icons/hicolor/64x64/hatta.png')))
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

        # Global wiki settings
        host = self.config.get('interface')
        port = int(self.config.get('port'))
        self.url = 'http://%s:%d/' % (host, port)

        self.preferences_window = PreferenceWindow(self, self.config)
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

        if pybonjour:
            self.zeroconf_thread = ZeroconfThread(self.config,
                                                  self.on_new_services)
            self.zeroconf_thread.start()
        else:
            self.zeroconf_thread = None
            self.on_new_services([])

    def _prepare_default_menu(self):
        """Creates and populates the context menu."""
        action = QAction(_(u'&Preferences'), self)
        action.setToolTip(_(u'Lets you configure the wiki.'))
        if sys.platform == 'darwin':
            action.setShortcut(Qt.CTRL + Qt.Key_Comma)
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
        global app
        app.quit()

    pyqtSlot(Exception)
    def on_error(self, erro):
        """Displays errors from exceptions."""
        QMessageBox.critical(None, 'Test title', 'Test content', 1, 2)

    def _make_discovery_action(self, name, host, port):
        """Creates a menu action from a discovered wiki."""
        action = QAction(_(u'%s on %s') % (
            '    ' + name, host), self)
        action.setToolTip(_(u'Opens %s in browser.') % name)
        action.triggered.connect((lambda x, y: lambda: webbrowser.open(
                'http://%s:%d' % (x, y)))(host, port))
        return action

    pyqtSlot(set)
    def on_new_services(self, services):
        """Displays discovered services in menu."""
        self.menu.clear()

        if len(services) > 0:
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

        self.menu.addActions(self.default_actions)
        self.menu.setDisabled(False)

default_config = WikiConfig(
    # Here you can modify the configuration: uncomment and change
    # the ones you need. Note that it's better use environment
    # variables or command line switches.

    interface='',
    port=8080,
    site_name='Hatta Wiki',
    pages_path=join(user_data_dir(
        name,
        organization),
        u'pages'),
    cache_path=user_cache_dir(
        name,
        organization),
    # front_page = 'Home'
    # page_charset = 'UTF-8'
)

class PreferenceWindow(QWidget):
    """Panel with most important preferences editable to user."""

    config_change = pyqtSignal(unicode, unicode, int)

    def __init__(self, parent, config):
        super(PreferenceWindow, self).__init__(
            None,
            Qt.Window | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint
            | Qt.WindowTitleHint)

        # Preferences data
        self.wiki_name = config.get('site_name',
                                    _(u'Enter the name of your wiki'))
        self.wiki_page_path = config.get('pages_path',
                                         _(u'Choose path for wiki pages'))
        self.wiki_port = int(config.get('port', 8080))

        # Set up GUI code
        self.setWindowTitle(_(u'Hatta preferences'))
        self.setWindowModality(Qt.WindowModal)

        self.main_vbox = QVBoxLayout(self)
        grid_layout = QGridLayout()
        # Wiki name input
        tooltip = _(u'Sets the name of you wiki. The name will be visible '
                   u'all accross the wiki and in wiki discovery.')
        self.name_label = QLabel(_(u'Wiki name:'), self)
        self.name_label.setToolTip(tooltip)
        self.name_edit = QLineEdit(self.wiki_name, self)
        self.name_edit.setToolTip(tooltip)
        grid_layout.addWidget(self.name_label, 0, 0)
        grid_layout.addWidget(self.name_edit, 0, 1)

        # Pages dir choosing
        tooltip = _(u'Sets the pages directory, where wiki pages will be'
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
        tooltip = _(u'Sets the port on which wiki is listening on.')
        self.port_label = QLabel(_(u'Listen port:'))
        self.port_label.setToolTip(tooltip)
        self.port_spin = QSpinBox(self)
        self.port_spin.setRange(1025, 65536)
        self.port_spin.setValue(self.wiki_port)
        self.port_spin.setToolTip(tooltip)
        grid_layout.addWidget(self.port_label, 2, 0)
        grid_layout.addWidget(self.port_spin, 2, 1)

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
        self.config_change.emit(
            unicode(self.name_edit.text()),
            unicode(self.pages_edit.text()),
            int(self.port_spin.value()))

if __name__ == '__main__':
    try:
        global _
        _ = gettext.translation('hatta', fallback=True).ugettext

        app = QApplication(sys.argv)
        QApplication.setQuitOnLastWindowClosed(False)
        status_icon = HattaTrayIcon()
        app.exec_()
    except KeyboardInterrupt:
        pass

