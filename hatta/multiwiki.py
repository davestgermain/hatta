"""
Wsgi application that supports multiple Hatta wikis.
Each domain is configured by a hatta wiki config file
in the HATTA_CONFIG_DIR directory
"""
import os, os.path
import glob

import hatta
import werkzeug
from configparser import ConfigParser
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.middleware.dispatcher import DispatcherMiddleware


class MultiWiki(ProxyFix):
    """
    WSGI app for dispatching multiple wikis based on domain.
    Each domain is configured in a section of the config file.
    """

    def __init__(self, config_file=os.environ.get('HATTA_CONFIG_FILE')):
        ProxyFix.__init__(self, self.host_dispatcher_app, x_prefix=1)
        self.apps = {}
        assert config_file is not None, "Configuration file is required"
        self.load_from_file(config_file)

    def load_from_file(self, config_file):
        config = ConfigParser()
        config.read(config_file)
        for section in config:
            if section == 'DEFAULT':
                continue
            wiki_config = hatta.WikiConfig()
            wiki_config.parse_options(config[section].items())
            wiki = hatta.Wiki(wiki_config, site_id=section)
            splitname = section.split('/', 1)

            domain_name = splitname[0].lower()
            if len(splitname) == 2:
                self.apps.setdefault(domain_name, DispatcherMiddleware(self.default_application, None)).mounts['/' + splitname[1]] = wiki.application
            else:
                self.apps[domain_name] = wiki.application

    def host_dispatcher_app(self, env, start):
        host = env.get('HTTP_HOST').split(':')[0].lower()
        try:
            app = self.apps[host]
        except KeyError:
            app = self.default_application
        return app(env, start)

    @werkzeug.wsgi.responder
    def default_application(self, environ, start_response):
        return werkzeug.Response()

