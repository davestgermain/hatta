"""
Wsgi application that supports multiple Hatta wikis.
Each domain is configured by a hatta wiki config file
in the HATTA_CONFIG_DIR directory
"""
import os, os.path
import glob

import hatta
import werkzeug
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.middleware.dispatcher import DispatcherMiddleware


class MultiWiki(ProxyFix):
    """
    WSGI app for dispatching multiple wikis based on domain.
    Each domain is configured with its own config file.
    """

    def __init__(self, config_dir=os.environ.get('HATTA_CONFIG_DIR')):
        ProxyFix.__init__(self, self.host_dispatcher_app, x_prefix=1)
        self.apps = {}
        self.load_config_files(config_dir)

    def load_config_files(self, config_dir):
        for conf_file in glob.glob(os.path.join(config_dir, '*.conf')):
            self.load_from_config(conf_file)

    def load_from_config(self, conf_file):
        config = hatta.WikiConfig()
        config.parse_files([conf_file])
        config.sanitize()
        wiki = hatta.Wiki(config, site_id=conf_file)

        # file name is the domain name _path
        # if the path is set, use the dispatcher middleware
        splitname = os.path.basename(os.path.splitext(conf_file)[0]).split('_', 1)
        domain_name = splitname[0]
        if len(splitname) == 2:
            self.apps.setdefault(domain_name, DispatcherMiddleware(self.default_application, None)).mounts['/' + splitname[1].replace('_', '/')] = wiki.application
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

