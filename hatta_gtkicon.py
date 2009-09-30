#!/usr/bin/env python
# -*- coding: utf-8 -*-

import hatta
import webbrowser
import urllib
import wsgiref.simple_server
import threading
import time

try:
    import gtk
except ImportError:
    gtk = None

try:
    import dbus
    import dbus.mainloop.glib
    import avahi
except ImportError:
    avahi = None

class StatusIcon(object):
    def __init__(self, url):
        self.url = url
        loader = gtk.gdk.PixbufLoader()
        loader.write(hatta.Wiki.icon)
        loader.close()
        self.icon = gtk.StatusIcon()
        self.icon.set_from_pixbuf(loader.get_pixbuf())
        self.icon.set_tooltip('Hatta Wiki')
        self.icon.connect_object('activate', self.on_activate, None)
        self.icon.connect_object('popup-menu', self.on_popup, None)
        self.urls = {}


    def on_activate(self, status_icon, data=None):
        webbrowser.open(self.url)

    def on_popup(self, status_icon, button, activate_time):
        menu = gtk.Menu()

        if self.urls:
            for name, url in self.urls.iteritems():
                item = gtk.MenuItem(name)
                item.connect('activate', self.url_on_activate, url)
                item.set_tooltip_text(url)
                menu.append(item)
                item.show()
            separator = gtk.SeparatorMenuItem()
            menu.append(separator)
            separator.show()

        browser = gtk.ImageMenuItem(gtk.STOCK_OPEN)
        browser.connect('activate', self.on_activate, False)
        menu.append(browser)
        browser.show()

        quit = gtk.ImageMenuItem(gtk.STOCK_CLOSE)
        quit.connect('activate', self.quit_on_activate, False)
        menu.append(quit)
        quit.show()

        menu.show()
        menu.popup(None, None, None, button, activate_time)

    def quit_on_activate(self, item, data=None):
        gtk.main_quit()

    def url_on_activate(self, item, data=None):
        webbrowser.open(data)

class AvahiService(object):
    def __init__(self, name, host=None, port=8080, services={}):
        if not host:
            host = ''
        self.services = services
        self.service_name = name
        # See http://www.dns-sd.org/ServiceTypes.html
        self.service_type = "_http._tcp"
        self.service_port = port
        self.service_txt = "hatta-wiki"
        self.domain = "" # Domain to publish on, default to .local
        self.host = host # Host to publish records for, default to localhost
        self.group = None #our entry group
        # Counter so we only rename after collisions a sensible number of times
        self.rename_count = 12

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SystemBus()
        self.server = dbus.Interface(
                self.bus.get_object(avahi.DBUS_NAME, avahi.DBUS_PATH_SERVER),
                avahi.DBUS_INTERFACE_SERVER)
        self.server.connect_to_signal("StateChanged", self.server_state_changed)
        self.server_state_changed(self.server.GetState())
        sbrowser = dbus.Interface(self.bus.get_object(avahi.DBUS_NAME,
        self.server.ServiceBrowserNew(avahi.IF_UNSPEC,
            avahi.PROTO_UNSPEC, self.service_type, 'local', dbus.UInt32(0))),
            avahi.DBUS_INTERFACE_SERVICE_BROWSER)
        sbrowser.connect_to_signal("ItemNew", self.new_item)
        sbrowser.connect_to_signal("ItemRemove", self.remove_item)


    def add_service(self):
        if self.group is None:
            self.group = dbus.Interface(
                    self.bus.get_object(avahi.DBUS_NAME,
                                        self.server.EntryGroupNew()),
                                        avahi.DBUS_INTERFACE_ENTRY_GROUP)
            self.group.connect_to_signal('StateChanged',
                                         self.entry_group_state_changed)
        print "Adding service '%s' of type '%s' ..." % (self.service_name,
                                                        self.service_type)
        self.group.AddService(
                avahi.IF_UNSPEC,    #interface
                avahi.PROTO_UNSPEC, #protocol
                dbus.UInt32(0),                  #flags
                self.service_name, self.service_type,
                self.domain, self.host,
                dbus.UInt16(self.service_port),
                avahi.string_array_to_txt_array(self.service_txt))
        self.group.Commit()

    def remove_service(self):
        if not self.group is None:
            self.group.Reset()

    def close(self):
        if not self.group is None:
            self.group.Free()

    def server_state_changed(self, state):
        if state == avahi.SERVER_COLLISION:
            print "WARNING: Server name collision"
            self.remove_service()
        elif state == avahi.SERVER_RUNNING:
            self.add_service()

    def entry_group_state_changed(self, state, error):
        print "state change: %i" % state

        if state == avahi.ENTRY_GROUP_ESTABLISHED:
            print "Service established."
        elif state == avahi.ENTRY_GROUP_COLLISION:
            self.rename_count = self.rename_count - 1
            if self.rename_count > 0:
                self.service_name = server.GetAlternativeServiceName(
                    self.service_name)
                print "WARNING: Service name collision, changing name to '%s' ..." % self.service_name
                self.remove_service()
                self.add_service()
            else:
                print "ERROR: No suitable service name found after %i retries, exiting." % 12
                gtk.main_quit()
        elif state == avahi.ENTRY_GROUP_FAILURE:
            print "Error in group state changed", error
            gtk.main_quit()

    def new_item(self, interface, protocol, name, stype, domain, flags):
        print "Found service '%s' type '%s' domain '%s' " % (name, stype, domain)
        if flags & avahi.LOOKUP_RESULT_LOCAL:
                # local service, skip
                pass
        self.server.ResolveService(interface, protocol, name, stype,
            domain, avahi.PROTO_UNSPEC, dbus.UInt32(0),
            reply_handler=self.new_service_resolved, error_handler=self.print_error)

    def remove_item(self, interface, protocol, name, stype, domain, flags):
        try:
            del self.services[name]
        except KeyError:
            pass

    def new_service_resolved(self, *args):
        url = 'http://%s:%d/' % (args[7], args[8])
        self.services[args[2]] = url

    def print_error(self, *args):
        print 'error_handler'
        print args[0]

class WikiServer(threading.Thread):
    def __init__(self, config, host, port):
        super(WikiServer, self).__init__()
        self.config = config
        self.port = port
        self.wiki = hatta.Wiki(config)
        self.server = wsgiref.simple_server.make_server(
                        host, port, self.wiki.application)

    def run(self):
        while not self.wiki.dead:
            self.server.handle_request()


def main():
    config = hatta.WikiConfig(
        # Here you can modify the configuration: uncomment and change
        # the ones you need. Note that it's better use environment
        # variables or command line switches.

        # interface=''
        # port=8080
        # pages_path = 'docs'
        # cache_path = 'cache'
        # front_page = 'Home'
        # site_name = 'Hatta Wiki'
        # page_charset = 'UTF-8'
    )
    config.parse_args()
    config.parse_files()
    port = int(config.get('port', 8080))
    host = config.get('interface', '')
    name = config.get('site_name', 'Hatta Wiki')
    url = 'http://%s:%d' % (host or 'localhost', port)
    thread = WikiServer(config, host, port)
    thread.start()
    if gtk:
        gtk.gdk.threads_init()
        status_icon = StatusIcon(url)
        if avahi:
            try:
                service = AvahiService(name, host, port, status_icon.urls)
            except dbus.exceptions.DBusException:
                service = None
        gtk.main()
        if avahi and service:
            service.close()
    else:
        webbrowser.open(url)
        try:
            while True:
                time.sleep(100)
        except KeyboardInterrupt:
            pass
    urllib.urlopen('/'.join([url, 'off-with-his-head'])).read(1)
    thread.join()

if __name__ == "__main__":
    main()
