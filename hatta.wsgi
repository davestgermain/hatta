#!/usr/bin/python
import hatta

config = hatta.WikiConfig(
    pages_path='/path/to/pages/', # XXX Edit this!
    cache_path='/path/to/cache/', # XXX Edit this!
)
application = hatta.Wiki(config).application
