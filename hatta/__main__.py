#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import sys

from hatta.config import read_config
from hatta.wiki import Wiki


# Avoid WSGI errors, see http://mercurial.selenic.com/bts/issue1095
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__


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
    name = wiki.site_name
    server = wsgiserver.CherryPyWSGIServer((host, port), app,
                                           server_name=name)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()

if __name__ == "__main__":
    main()
