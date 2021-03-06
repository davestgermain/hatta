import datetime
import io
import time
import os, os.path
import mimetypes
import threading

from .. import error, page
from werkzeug.urls import url_quote, url_unquote


class StorageError(Exception):
    """Thrown when there are problems with configuration of storage."""


def merge_func(base, other, this):
    """Used for merging edit conflicts."""
    import mercurial.simplemerge
    if (base.isbinary() or
        other.isbinary()):
        raise ValueError("can't merge binary data")
    m3 = mercurial.simplemerge.Merge3Text(base.data(), this, other.data())
    return b''.join(m3.merge_lines(start_marker=b'<<<<<<< local',
                                  mid_marker=b'=======',
                                  end_marker=b'>>>>>>> other',
                                  base_marker=None))


class Revision:
    """
    Encapsulates page data and metadata
    """

    def __init__(self, *args, charset='utf8', **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.charset = charset

    @property
    def file(self):
        return io.BytesIO(self.data)

    @property
    def text(self):
        text = str(self.data, self.charset, 'replace')
        return text


class BaseWikiStorage(threading.local):
    """
    Provides means of storing wiki pages and keeping track of their
    change history, using database repository as the storage method.
    """

    def __init__(self, charset=None, _=lambda x: x, unix_eol=False,
                 extension=None, **kwargs):
        """

        """
        threading.local.__init__(self)
        self._ = _
        self.charset = charset or 'utf-8'
        self.unix_eol = unix_eol
        self.extension = extension
        self.repo_prefix = kwargs.get('repo_prefix', '')

        self._repo = self._tip = self._current_rev = None

    @property
    def repo(self):
        if self._repo is None:
            self._repo = self.open_repo()
        return self._repo

    @repo.setter
    def repo(self, obj):
        self._repo = obj

    @property
    def tip(self):
        if self._tip is None:
            self._tip = self.get_tip()
        return self._tip

    @tip.setter
    def tip(self, obj):
        self._tip = obj

    @property
    def repo_revision(self):
        """
        Return current repository revision
        """
        if self._current_rev is None or self._repo is None:
            self._current_rev = self.get_repo_rev()
        return self._current_rev

    @repo_revision.setter
    def repo_revision(self, rev):
        self._current_rev = rev

    def reopen(self):
        self.repo.close()
        self.tip = None
        self.repo = None
        self.repo_revision = None

    def get_tip(self):
        raise NotImplementedError()

    def open_repo(self):
        raise NotImplementedError()

    def get_cache_path(self):
        raise NotImplementedError()

    def get_index_path(self):
        raise NotImplementedError()

    def __contains__(self, title):
        raise NotImplementedError()

    def get_revision(self, title, rev=None):
        raise NotImplementedError()

    def get_previous_revision(self, title, current_rev):
        """
        Get the revision earlier than this one.
        """
        if current_rev.isdigit():
            return self.get_revision(title, int(current_rev) - 1)
        else:
            raise NotImplementedError()

    def delete_page(self, title, author, comment, ts=None):
        raise NotImplementedError()

    def page_history(self, title):
        """Iterate over the page's history."""
        raise NotImplementedError()

    def history(self):
        """Iterate over the history of entire wiki.
        path, rev, creation_date, owner, comment
        """
        raise NotImplementedError()

    def all_pages(self):
        """Iterate over the titles of all pages in the wiki."""
        raise NotImplementedError()

    def changed_since(self, rev):
        """
        Return all pages that changed since specified repository revision.
        """
        raise NotImplementedError()

    def save_data(self, title, data, author=None, comment=None, parent_rev=None, ts=None, new=False):
        """Save a new revision of the page. If the data is None, deletes it."""
        _ = self._
        user = author or _('anon')
        text = comment or _('comment')

        ts = ts or datetime.datetime.utcnow()
        if data is None:
            if title not in self:
                raise error.ForbiddenErr()
            else:
                return self.delete_page(title, user, text, ts=ts)
        # else:
        #     if other is not None:
        #         try:
        #             data = self._merge(repo_file, parent, other, data)
        #         except ValueError:
        #             text = _(u'failed merge of edit conflict').encode('utf-8')
        return data, user, text, ts

    def save_text(self, title, text, author='', comment='', parent=None):
        """Save text as specified page, encoded to charset."""

        data = text.encode(self.charset)
        if self.unix_eol:
            data = data.replace(b'\r\n', b'\n')
        self.save_data(title, data, author, comment, parent)

    def page_meta(self, title):
        """Get page's revision, date, last editor and his edit comment."""
        revision = self.get_revision(title)
        return revision.rev, revision.date, revision.author, revision.comment

    def revision_text(self, title, rev):
        """Get unicode text of the specified revision of the page."""

        data = self.page_revision(title, rev)
        try:
            text = str(data, self.charset)
        except UnicodeDecodeError:
            text = self._('Unable to display')
        return text

    def __iter__(self):
        return self.all_pages()

    def _title_to_file(self, title):
        title = str(title).strip()
        filename = url_quote(title, safe='', unsafe='~')
        # Escape special windows filenames and dot files
        _windows_device_files = ('CON', 'AUX', 'COM1', 'COM2', 'COM3',
                                 'COM4', 'LPT1', 'LPT2', 'LPT3', 'PRN',
                                 'NUL')
        if (filename.split('.')[0].upper() in _windows_device_files or
            filename.startswith('_') or filename.startswith('.')):
            filename = '_' + filename
        if page.page_mime(title) == 'text/x-wiki' and self.extension:
            filename += self.extension
        return os.path.join(self.repo_prefix, filename)

    def _file_to_title(self, filepath):
        sep = os.path.sep
        name = filepath[len(self.repo_prefix):].strip(sep)
        # Un-escape special windows filenames and dot files
        if name.startswith('_') and len(name) > 1:
            name = name[1:]
        if self.extension and name.endswith(self.extension):
            name = name[:-len(self.extension)]
        return url_unquote(name)

    def __enter__(self):
        self.reopen()
        return self

    def __exit__(self, type, value, tb):
        self.reopen()
