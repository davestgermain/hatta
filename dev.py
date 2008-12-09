#!/usr/bin/python
# -*- coding: utf-8 -*-

import hatta
import werkzeug

config = WikiConfig(
    # Here you can modify the configuration: uncomment and change the ones
    # you need. Note that it's better use environment variables or command
    # line switches.

    # interface='',
    # port=8080,
    # pages_path = 'docs',
    # cache_path = 'cache',
    # front_page = 'Home',
    # site_name = 'Hatta Wiki',
    # page_charset = 'UTF-8',
)
config._parse_args()
application = Wiki(config).application
host, port = config.interface or 'localhost', int(config.port)
werkzeug.run_simple(config.interface, port, application, use_reloader=True)
