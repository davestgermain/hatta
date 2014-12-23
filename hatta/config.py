#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import mercurial


OPTIONS = []
VALID_NAMES = set()


def _add(short, long, dest, help, default=None, metavar=None,
         action=None, type=None):
    """Helper for building the list of options."""

    OPTIONS.append((short, long, dest, help, default, metavar, action, type))
    VALID_NAMES.add(dest)

_add('-V', '--version', dest='show_version', default=False,
    help='Display version and exit', action="store_true")
_add('-d', '--pages-dir', dest='pages_path',
    help='Store pages in DIR', metavar='DIR')
_add('-R', '--repo-dir', dest='repo_path',
    help='Use the repository at DIR', metavar='DIR')
_add('-t', '--cache-dir', dest='cache_path',
    help='Store cache in DIR', metavar='DIR')
_add('-T', '--template-dir', dest='template_path',
    help='Use templates in DIR', metavar='DIR')
_add('-i', '--interface', dest='interface',
    help='Listen on interface INT', metavar='INT')
_add('-p', '--port', dest='port', type='int',
    help='Listen on port PORT', metavar='PORT')
_add('-s', '--script-name', dest='script_name',
    help='Override SCRIPT_NAME to NAME', metavar='NAME')
_add('-n', '--site-name', dest='site_name',
    help='Set the name of the site to NAME', metavar='NAME')
_add('-m', '--front-page', dest='front_page',
    help='Use PAGE as the front page', metavar='PAGE')
_add('-a', '--alias-page', dest='alias_page',
    help='Use PAGE as the alias page', metavar='PAGE')
_add('-H', '--help-page', dest='help_page',
    help='Use PAGE as the editor help text', metavar='PAGE')
_add('-e', '--encoding', dest='page_charset',
    help='Use encoding ENC to read and write pages', metavar='ENC')
_add('-c', '--config-file', dest='config_file',
    help='Read configuration from FILE', metavar='FILE')
_add('-l', '--language', dest='language',
    help='Translate interface to LANG', metavar='LANG')
_add('-r', '--read-only', dest='read_only',
    help='Whether the wiki should be read-only', action="store_true")
_add('-f', '--fallback-url', dest='fallback_url',
    help='Redirect to URL on 404', metavar="URL")
_add('-g', '--icon-page', dest='icon_page', metavar="PAGE",
    help='Read icons graphics from PAGE.')
_add('-w', '--hgweb', dest='hgweb',
    help='Enable hgweb access to the repository', action="store_true")
_add('-W', '--wiki-words', dest='wiki_words',
    help='Enable WikiWord links', action="store_true")
_add('-I', '--ignore-indent', dest='ignore_indent',
    help='Treat indented lines as normal text', action="store_true")
_add('-M', '--math-url', dest='math_url',
    help='Use the URL for rendering the equations. Empty to disable math.',
    metavar='URL')
_add('-P', '--pygments-style', dest='pygments_style',
    help='Use the STYLE pygments style for highlighting',
    metavar='STYLE')
_add('-D', '--subdirectories', dest='subdirectories',
    action="store_true",
    help='Store subpages as subdirectories in the filesystem')
_add('-E', '--extension', dest='extension',
    help='Extension to add to wiki page files')
_add('-U', '--unix-eol', dest='unix_eol',
    action="store_true",
    help='Convert all text pages to UNIX-style CR newlines')
_add('', '--recaptcha-public-key', dest='recaptcha_public_key',
    metavar='KEY',
    help='A public key KEY for ReCAPTCHA service.')
_add('', '--recaptcha-private-key', dest='recaptcha_private_key',
    metavar='KEY',
    help='A private key KEY for ReCAPTCHA service.')


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

    def __init__(self, **kw):
        self.config = dict(kw)
        self.valid_names = set(VALID_NAMES)
        self.parse_environ()
        self.options = list(OPTIONS)

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
                if name in self.valid_names:
                    self.config[name] = value

    def parse_args(self):
        """Check the commandline arguments for options."""

        import optparse

        parser = optparse.OptionParser()
        for (short, long, dest, help, default, metavar, action,
             type) in self.options:
            parser.add_option(short, long, dest=dest, help=help, type=type,
                              default=default, metavar=metavar, action=action)

        options, args = parser.parse_args()
        for option, value in options.__dict__.iteritems():
            if value is not None:
                self.config[option] = value
        if args:
            self.config['pages_path'] = args[0]

    def parse_files(self, files=None):
        """Check the config files for options."""

        if files is None:
            files = [self.get('config_file', self.default_filename)]
        parser = mercurial.config.config()
        for path in files:
            try:
                parser.read(path)
            except IOError:
                pass
        section = 'hatta'
        try:
            options = parser.items(section)
        except KeyError:
            return
        for option, value in options:
            if option not in self.valid_names:
                raise ValueError('Invalid option name "%s".' % option)
            self.config[option] = value

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
