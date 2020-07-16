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


config_dir = os.environ['HATTA_CONFIG_DIR']
DEBUG = os.environ.get('DEBUG', '').lower() in ('true', 'on', 'yes')
DEFAULT_HOST = 'localhost'
APPS = {}


@werkzeug.wsgi.responder
def default_application(environ, start_response):
    return werkzeug.Response()


for conf_file in glob.glob(os.path.join(config_dir, '*.conf')):
    config = hatta.WikiConfig()
    config.parse_files([conf_file])
    config.sanitize()
    wsgi_app = hatta.Wiki(config).application

    # file name is the domain name _path
    # if the path is set, use the dispatcher middleware
    splitname = os.path.basename(os.path.splitext(conf_file)[0]).split('_', 1)
    domain_name = splitname[0]
    if DEBUG:
        import pprint
        print('/'.join(splitname))
        pprint.pprint(config.config)

    if len(splitname) == 2:
        APPS.setdefault(domain_name, DispatcherMiddleware(default_application, None)).mounts['/' + splitname[1]] = wsgi_app
    else:
        APPS[domain_name] = wsgi_app


def application(env, start):
    host = env.get('HTTP_HOST', DEFAULT_HOST).split(':')[0].lower()
    app = APPS.get(host, default_application)
    return app(env, start)

application = ProxyFix(application, x_prefix=1)
