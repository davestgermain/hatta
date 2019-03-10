#!/usr/bin/python
# -*- coding: utf-8 -*-

from flup.server.fcgi import WSGIServer
# uses https://bitbucket.org/lcrees/wsgigzip/
from wsgigzip.gzip import GzipMiddleware
import hatta

config = hatta.WikiConfig(
    pages_path = '/path/to/pages/', # edit this
    cache_path = '/path/to/cache/', # edit this
    template_path = '/path/to/templates/', # optional
    pygments_style = 'autumn', # optional
    subdirectories = True # optional
)

config.parse_args()
config.parse_files()
config.sanitize()
wiki = hatta.Wiki(config)

WSGIServer(GzipMiddleware(wiki.application)).run()
