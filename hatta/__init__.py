#!/usr/bin/env python
# -*- coding: utf-8 -*-

# @copyright: 2008-2009 Radomir Dopieralski <hatta@sheep.art.pl>
# @license: GNU GPL, see COPYING for details.

"""
Hatta Wiki is a wiki engine designed to be used with Mercurial repositories.
It requires Mercurial and Werkzeug python modules.

Hatta's pages are just plain text files (and also images, binaries, etc.) in
some directory in your repository. For example, you can put it in your
project's "docs" directory to keep documentation. The files can be edited both
from the wiki or with a text editor -- in either case the changes committed to
the repository will appear in the recent changes and in page's history.

See hatta.py --help for usage.
"""

import datetime
import difflib
import mimetypes
import os
import re
import sys

# Avoid WSGI errors, see http://mercurial.selenic.com/bts/issue1095
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

from wiki import Wiki, WikiResponse, WikiRequest

__version__ = '1.4.0dev'
project_name = 'Hatta'
project_url = 'http://hatta-wiki.org/'
project_description = 'Wiki engine that lives in Mercurial repository.'

mimetypes.add_type('application/x-python', '.wsgi')
mimetypes.add_type('application/x-javascript', '.js')
mimetypes.add_type('text/x-rst', '.rst')

_ = lambda x: x # Later replaced with gettext initialization



class WikiConfig(object):
    """
    Responsible for reading and storing site configuration. Contains the
    default settings.

    >>> config = WikiConfig(port='2080')
    >>> config.sanitize()
    >>> config.get('port')
    2080
    """

    default_filename = u'hatta.conf'

    # Please see the bottom of the script for modifying these values.

    def __init__(self, **kw):
        self.config = dict(kw)
        self.parse_environ()

    def sanitize(self):
        """
        Convert options to their required types.
        """

        try:
            self.config['port'] = int(self.get('port', 0))
        except ValueError:
            self.config['port'] = 8080

    def parse_environ(self):
        """Check the environment variables for options."""

        prefix = 'HATTA_'
        for key, value in os.environ.iteritems():
            if key.startswith(prefix):
                name = key[len(prefix):].lower()
                self.config[name] = value

    def parse_args(self):
        """Check the commandline arguments for options."""

        import optparse

        self.options = []
        parser = optparse.OptionParser()

        def add(*args, **kw):
            self.options.append(kw['dest'])
            parser.add_option(*args, **kw)

        add('-V', '--version', dest='show_version', default=False,
            help='Display version and exit', action="store_true")
        add('-d', '--pages-dir', dest='pages_path',
            help='Store pages in DIR', metavar='DIR')
        add('-t', '--cache-dir', dest='cache_path',
            help='Store cache in DIR', metavar='DIR')
        add('-i', '--interface', dest='interface',
            help='Listen on interface INT', metavar='INT')
        add('-p', '--port', dest='port', type='int',
            help='Listen on port PORT', metavar='PORT')
        add('-s', '--script-name', dest='script_name',
            help='Override SCRIPT_NAME to NAME', metavar='NAME')
        add('-n', '--site-name', dest='site_name',
            help='Set the name of the site to NAME', metavar='NAME')
        add('-m', '--front-page', dest='front_page',
            help='Use PAGE as the front page', metavar='PAGE')
        add('-e', '--encoding', dest='page_charset',
            help='Use encoding ENC to read and write pages', metavar='ENC')
        add('-c', '--config-file', dest='config_file',
            help='Read configuration from FILE', metavar='FILE')
        add('-l', '--language', dest='language',
            help='Translate interface to LANG', metavar='LANG')
        add('-r', '--read-only', dest='read_only',
            help='Whether the wiki should be read-only', action="store_true")
        add('-g', '--icon-page', dest='icon_page', metavar="PAGE",
            help='Read icons graphics from PAGE.')
        add('-w', '--hgweb', dest='hgweb',
            help='Enable hgweb access to the repository', action="store_true")
        add('-W', '--wiki-words', dest='wiki_words',
            help='Enable WikiWord links', action="store_true")
        add('-I', '--ignore-indent', dest='ignore_indent',
            help='Treat indented lines as normal text', action="store_true")
        add('-P', '--pygments-style', dest='pygments_style',
            help='Use the STYLE pygments style for highlighting',
            metavar='STYLE')
        add('-D', '--subdirectories', dest='subdirectories',
            action="store_true",
            help='Store subpages as subdirectories in the filesystem')

        options, args = parser.parse_args()
        for option, value in options.__dict__.iteritems():
            if option in self.options:
                if value is not None:
                    self.config[option] = value

    def parse_files(self, files=None):
        """Check the config files for options."""

        import ConfigParser

        if files is None:
            files = [self.get('config_file', self.default_filename)]
        parser = ConfigParser.SafeConfigParser()
        parser.read(files)
        for section in parser.sections():
            for option, value in parser.items(section):
                self.config[option] = value

    def save_config(self, filename=None):
        """Saves configuration to a given file."""
        if filename is None:
            filename = self.default_filename

        import ConfigParser
        parser = ConfigParser.RawConfigParser()
        section = self.config['site_name']
        parser.add_section(section)
        for key, value in self.config.iteritems():
            parser.set(section, str(key), str(value))

        configfile = open(filename, 'wb')
        try:
            parser.write(configfile)
        finally:
            configfile.close()

    def get(self, option, default_value=None):
        """
        Get the value of a config option or default if not set.

        >>> config = WikiConfig(option=4)
        >>> config.get("ziew", 3)
        3
        >>> config.get("ziew")
        >>> config.get("ziew", "ziew")
        'ziew'
        >>> config.get("option")
        4
        """

        return self.config.get(option, default_value)

    def get_bool(self, option, default_value=False):
        """
        Like get, only convert the value to True or False.
        """

        value = self.get(option, default_value)
        if value in (
            1, True,
            'True', 'true', 'TRUE',
            '1',
            'on', 'On', 'ON',
            'yes', 'Yes', 'YES',
            'enable', 'Enable', 'ENABLE',
            'enabled', 'Enabled', 'ENABLED',
        ):
            return True
        elif value in (
            None, 0, False,
            'False', 'false', 'FALSE',
            '0',
            'off', 'Off', 'OFF',
            'no', 'No', 'NO',
            'disable', 'Disable', 'DISABLE',
            'disabled', 'Disabled', 'DISABLED',
        ):
            return False
        else:
            raise ValueError("expected boolean value")

    def set(self, key, value):
        self.config[key] = value



def read_config():
    """Read and parse the config."""

    config = WikiConfig(
        # Here you can modify the configuration: uncomment and change the ones
        # you need. Note that it's better use environment variables or command
        # line switches.

        # interface='',
        # port=8080,
        # pages_path = 'docs',
        # front_page = 'Home',
        # site_name = 'Hatta Wiki',
        # page_charset = 'UTF-8',
    )
    config.parse_args()
    config.parse_files()
    # config.sanitize()
    return config

def application(env, start):
    """Detect that we are being run as WSGI application."""

    global application
    config = read_config()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if config.get('pages_path') is None:
        config.set('pages_path', os.path.join(script_dir, 'docs'))
    wiki = Wiki(config)
    application = wiki.application
    return application(env, start)

def main(config=None, wiki=None):
    """Start a standalone WSGI server."""

    config = config or read_config()
    wiki = wiki or Wiki(config)
    app = wiki.application

    host, port = (config.get('interface', '0.0.0.0'),
                  int(config.get('port', 8080)))
    try:
        from cherrypy import wsgiserver
    except ImportError:
        try:
            from cherrypy import _cpwsgiserver as wsgiserver
        except ImportError:
            import wsgiref.simple_server
            server = wsgiref.simple_server.make_server(host, port, app)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            return
    apps = [('', app)]
    name = wiki.site_name
    server = wsgiserver.CherryPyWSGIServer((host, port), apps, server_name=name)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()

if __name__ == "__main__":
    main()
