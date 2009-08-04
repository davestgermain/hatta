"""
A single function that is being run as a separate process by Hatta system 
tray icon. The process starts a standolone wiki server.
"""

from wsgiref.simple_server import make_server
import hatta
from hatta_qticon import config

def start_wiki(config):
    """Starts a wiki instance hopefully in another process."""
    wiki = hatta.Wiki(config)
    server = make_server(
            config.get('interface', ''),
            int(config.get('port', '8080')),
            wiki.application)
    while not wiki.dead:
        server.handle_request()


if __name__ == '__main__':
    start_wiki(config)
