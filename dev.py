#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
An auto-reloading standalone wiki server, useful for development.
"""

import hatta
import werkzeug

if __name__=="__main__":
    config = hatta.WikiConfig()
    config.parse_args()
    config.parse_files()
    config.sanitize()
    application = hatta.Wiki(config).application
    host, port = config.interface or 'localhost', int(config.port)
    werkzeug.run_simple(host, port, application, use_reloader=True)
