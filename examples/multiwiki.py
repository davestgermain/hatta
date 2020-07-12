import hatta
import os, os.path
import glob

config_dir = os.environ['HATTA_CONFIG_DIR']
DEFAULT_HOST = 'localhost'
APPS = {}

for conf_file in glob.glob(os.path.join(config_dir, '*.conf')):
    config = hatta.WikiConfig()
    config.parse_files(conf_file)
    config.sanitize()
    # file name is the domain name
    APPS[os.path.splitext(conf_file)[0]] = hatta.Wiki(config).application


def application(env, start):
    host = env.get('HTTP_HOST', DEFAULT_HOST).split(':')[0].lower()
    app = APPS.get(host)
    return app(env, start)
