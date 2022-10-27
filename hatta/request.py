# -*- coding: utf-8 -*-

from werkzeug.urls import url_unquote
from werkzeug.wrappers import Request
import hatta.views


class WikiRequest(Request):
    """
    A Werkzeug's request with additional functions for handling file
    uploads and wiki-specific link generation.
    """

    charset = 'utf-8'
    encoding_errors = 'ignore'

    def __init__(self, wiki, adapter, environ, **kw):
        Request.__init__(self, environ, shallow=False, **kw)
        self.wiki = wiki
        self.adapter = adapter

    def get_url(self, title=None, view=None, method='GET',
                external=False, **kw):
        if view is None:
            view = 'view'
        if title is not None:
            kw['title'] = title.strip()
        return self.adapter.build(view, kw, method=method,
                                  force_external=external)

    def get_download_url(self, title):
        return self.get_url(title, 'download')

    def get_author(self):
        """Try to guess the author name. Use IP address as last resort."""

        try:
            cookie = url_unquote(self.cookies.get("author", ""))
        except UnicodeError:
            cookie = None
        try:
            auth = url_unquote(self.environ.get('REMOTE_USER', ""))
        except UnicodeError:
            auth = None
        author = (self.form.get("author") or cookie or auth or
                  self.remote_addr)
        return author

