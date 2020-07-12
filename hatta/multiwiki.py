"""
Wsgi application that supports multiple Hatta wikis.
Each domain is configured by a hatta wiki config file
in the HATTA_CONFIG_DIR directory
"""
import os, os.path
import glob

import hatta
from werkzeug.middleware.proxy_fix import ProxyFix


config_dir = os.environ['HATTA_CONFIG_DIR']
DEBUG = os.environ.get('DEBUG', '').lower() in ('true', 'on', 'yes')
DEFAULT_HOST = 'localhost'
APPS = {}


for conf_file in glob.glob(os.path.join(config_dir, '*.conf')):
    config = hatta.WikiConfig()
    config.parse_files([conf_file])
    config.sanitize()
    # file name is the domain name
    domain_name = os.path.basename(os.path.splitext(conf_file)[0])
    if DEBUG:
        import pprint
        print(domain_name)
        pprint.pprint(config.config)
    APPS[domain_name] = ProxyFix(hatta.Wiki(config).application)


def application(env, start):
    host = env.get('HTTP_HOST', DEFAULT_HOST).split(':')[0].lower()
    app = APPS.get(host)
    return app(env, start)
