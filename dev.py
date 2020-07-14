#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
An auto-reloading standalone wiki server, useful for development.
"""

import hatta
import werkzeug
from werkzeug.middleware.profiler import ProfilerMiddleware

if __name__=="__main__":
    config = hatta.WikiConfig()
    config.parse_args()
#    config.parse_files()
    wiki = hatta.Wiki(config)


    application = wiki.application

    # application = ProfilerMiddleware(application)

    host = config.get('interface', 'localhost')
    port = int(config.get('port', 8080))
    werkzeug.run_simple(host, port, application, use_reloader=True)
