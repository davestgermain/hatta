#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
# XXX Uncomment and edit this if hatta.py is not installed in site-packages
#sys.path.insert(0, "/path/to/dir/with/hatta/")
import hatta

config = hatta.WikiConfig(
    pages_path='/path/to/pages/', # XXX Edit this!
    cache_path='/path/to/cache/', # XXX Edit this!
)
config.parse_args()
config.parse_files()
config.sanitize()
wiki = hatta.Wiki(config)
application = wiki.application
