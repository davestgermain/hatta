# -*- coding: utf-8 -*-

import os
import tempfile

import werkzeug


class WikiTempFile(object):
    """Wrap a file for uploading content."""

    def __init__(self, tmppath):
        self.tmppath = tempfile.mkdtemp(dir=tmppath)
        self.tmpname = os.path.join(self.tmppath, 'saved')
        self.f = open(self.tmpname, "wb")

    def read(self, *args, **kw):
        return self.f.read(*args, **kw)

    def readlines(self, *args, **kw):
        return self.f.readlines(*args, **kw)

    def write(self, *args, **kw):
        return self.f.write(*args, **kw)

    def seek(self, *args, **kw):
        return self.f.seek(*args, **kw)

    def truncate(self, *args, **kw):
        return self.f.truncate(*args, **kw)

    def close(self, *args, **kw):
        ret = self.f.close(*args, **kw)
        try:
            os.unlink(self.tmpname)
        except OSError:
            pass
        try:
            os.rmdir(self.tmppath)
        except OSError:
            pass
        return ret


class WikiRequest(werkzeug.BaseRequest, werkzeug.ETagRequestMixin):
    """
    A Werkzeug's request with additional functions for handling file
    uploads and wiki-specific link generation.
    """

    charset = 'utf-8'
    encoding_errors = 'ignore'

    def __init__(self, wiki, adapter, environ, **kw):
        werkzeug.BaseRequest.__init__(self, environ, shallow=False, **kw)
        self.wiki = wiki
        self.adapter = adapter
        self.tmpfiles = []
        self.tmppath = wiki.path

    def get_url(self, title=None, view=None, method='GET',
                external=False, **kw):
        if view is None:
            view = self.wiki.view
        if title is not None:
            kw['title'] = title.strip()
        return self.adapter.build(view, kw, method=method,
                                  force_external=external)

    def get_download_url(self, title):
        return self.get_url(title, view=self.wiki.download)

    def get_author(self):
        """Try to guess the author name. Use IP address as last resort."""

        try:
            cookie = werkzeug.url_unquote(self.cookies.get("author", ""))
        except UnicodeError:
            cookie = None
        try:
            auth = werkzeug.url_unquote(self.environ.get('REMOTE_USER', ""))
        except UnicodeError:
            auth = None
        author = (self.form.get("author") or cookie or auth or
                  self.remote_addr)
        return author

    def _get_file_stream(self, total_content_length=None, content_type=None,
                         filename=None, content_length=None):
        """Save all the POSTs to temporary files."""

        temp_file = WikiTempFile(self.tmppath)
        self.tmpfiles.append(temp_file)
        return temp_file

    def cleanup(self):
        """Clean up the temporary files created by POSTs."""

        for temp_file in self.tmpfiles:
            temp_file.close()
        self.tmpfiles = []


