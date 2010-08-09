#!/usr/bin/env python
# -*- coding: utf-8 -*-

# @copyright: 2008-2009 Radomir Dopieralski <hatta@sheep.art.pl>
# @license: GNU GPL, see COPYING for details.

"""
Hatta Wiki is a wiki engine designed to be used with Mercurial repositories.
It requires Mercurial and Werkzeug python modules.

Hatta's pages are just plain text files (and also images, binaries, etc.) in
some directory in your repository. For example, you can put it in your
project's "docs" directory to keep documentation. The files can be edited both
from the wiki or with a text editor -- in either case the changes committed to
the repository will appear in the recent changes and in page's history.

See hatta.py --help for usage.
"""

import os
import sys

# Avoid WSGI errors, see http://mercurial.selenic.com/bts/issue1095
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

from wiki import Wiki, WikiResponse, WikiRequest
from config import WikiConfig, read_config

__version__ = '1.4.0dev'
project_name = 'Hatta'
project_url = 'http://hatta-wiki.org/'
project_description = 'Wiki engine that lives in Mercurial repository.'


def application(env, start):
    """Detect that we are being run as WSGI application."""

    global application
    config = read_config()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if config.get('pages_path') is None:
        config.set('pages_path', os.path.join(script_dir, 'docs'))
    wiki = Wiki(config)
    application = wiki.application
    return application(env, start)

def main(config=None, wiki=None):
    """Start a standalone WSGI server."""

    config = config or read_config()
    wiki = wiki or Wiki(config)
    app = wiki.application

    host, port = (config.get('interface', '0.0.0.0'),
                  int(config.get('port', 8080)))
    try:
        from cherrypy import wsgiserver
    except ImportError:
        try:
            from cherrypy import _cpwsgiserver as wsgiserver
        except ImportError:
            import wsgiref.simple_server
            server = wsgiref.simple_server.make_server(host, port, app)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            return
    apps = [('', app)]
    name = wiki.site_name
    server = wsgiserver.CherryPyWSGIServer((host, port), apps, server_name=name)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()

if __name__ == "__main__":
    main()
