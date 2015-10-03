#!/usr/bin/python
# -*- coding: utf-8 -*-

import datetime
import os
import re
import thread
import werkzeug
import StringIO

# Note: we have to set these before importing Mercurial
os.environ['HGENCODING'] = 'utf-8'

import mercurial.commands
import mercurial.hg
import mercurial.hgweb
import mercurial.merge
import mercurial.revlog
import mercurial.ui
import mercurial.util
import mercurial.simplemerge
import mercurial.__version__

from hatta import error
from hatta import page


class StorageError(Exception):
    """Thrown when there are problems with configuration of storage."""


def locked_repo(func):
    """A decorator for locking the repository when calling a method."""

    def new_func(self, *args, **kwargs):
        """Wrap the original function in locks."""

        wlock = self.repo.wlock()
        lock = self.repo.lock()
        try:
            func(self, *args, **kwargs)
        finally:
            lock.release()
            wlock.release()
    return new_func


def _get_ui():
    try:
        ui = mercurial.ui.ui(report_untrusted=False,
                                  interactive=False, quiet=True)
    except TypeError:
        # Mercurial 1.3 changed the way we setup the ui object.
        ui = mercurial.ui.ui()
        ui.quiet = True
        ui._report_untrusted = False
        ui.setconfig('ui', 'interactive', False)
    return ui


def _get_memfilectx(repo, path, data, islink=False, isexec=False, copied=None, memctx=None):
    try:
        # For mercurial 3.2+
        return mercurial.context.memfilectx(
            repo=repo,
            path=path,
            data=data,
            islink=islink,
            isexec=isexec,
            memctx=memctx,
            copied=copied,
        )
    except TypeError:
        # For older mercurial
        return mercurial.context.memfilectx(
            path=path,
            data=data,
            islink=islink,
            isexec=isexec,
            copied=copied,
        )


def _file_deleted():
    if mercurial.__version__.version.startswith(('0.', '1.', '2.', '3.0', '3.1')):
        # For older mercurial
        raise IOError()
    # For mercurial 3.2+
    return None


def merge_func(base, other, this):
    """Used for merging edit conflicts."""

    if (mercurial.util.binary(this) or mercurial.util.binary(base) or
        mercurial.util.binary(other)):
        raise ValueError("can't merge binary data")
    m3 = mercurial.simplemerge.Merge3Text(base, this, other)
    return ''.join(m3.merge_lines(start_marker='<<<<<<< local',
                                  mid_marker='=======',
                                  end_marker='>>>>>>> other',
                                  base_marker=None))


def _get_datetime(filectx):
    """
    Create a datetime object for the changeset's cretion time, taking into
    account the timezones.
    """

    timestamp, offset = filectx.date()
    date = datetime.datetime.fromtimestamp(timestamp + offset)
    return date


class WikiStorage(object):
    """
    Provides means of storing wiki pages and keeping track of their
    change history, using Mercurial repository as the storage method.
    """

    def __init__(self, path, charset=None, _=lambda x: x, unix_eol=False,
                 extension=None, repo_path=None):
        """
        Takes the path to the directory where the pages are to be kept.
        If the directory doesn't exist, it will be created. If it's inside
        a Mercurial repository, that repository will be used, otherwise
        a new repository will be created in it.
        """

        self._ = _
        self.charset = charset or 'utf-8'
        self.unix_eol = unix_eol
        self.extension = extension
        self.path = os.path.abspath(path)
        if not os.path.exists(self.path):
            os.makedirs(self.path)
        self.ui = _get_ui()
        if repo_path is None:
            self.repo_path = self.path
        else:
            self.repo_path = os.path.abspath(repo_path)
            if not self.path.startswith(self.repo_path):
                raise StorageError(
                    "Page path %r is outside of the repository path %r." % (
                        self.path, self.repo_path))
        self.repo_prefix = self.path[len(self.repo_path):].strip('/')
        if not os.path.exists(os.path.join(self.repo_path, '.hg')):
            # Create the repository if needed.
            mercurial.hg.repository(self.ui, self.repo_path, create=True)
        self._repos = {}
        self._tips = {}

    def reopen(self):
        """Close and reopen the repo, to make sure we are up to date."""

        self._repos = {}
        self._tips = {}

    @property
    def repo(self):
        """Keep one open repository per thread."""

        thread_id = thread.get_ident()
        try:
            return self._repos[thread_id]
        except KeyError:
            repo = mercurial.hg.repository(self.ui, self.repo_path)
            self._repos[thread_id] = repo
            return repo

    def _title_to_file(self, title):
        title = unicode(title).strip()
        filename = werkzeug.url_quote(title, safe='')
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
        _ = self._
        if not filepath.startswith(self.repo_prefix):
            raise error.ForbiddenErr(
                _(u"Can't read or write outside of the pages repository"))
        name = filepath[len(self.repo_prefix):].strip('/')
        # Un-escape special windows filenames and dot files
        if name.startswith('_') and len(name) > 1:
            name = name[1:]
        if self.extension and name.endswith(self.extension):
            name = name[:-len(self.extension)]
        return werkzeug.url_unquote(name)

    def __contains__(self, title):
        repo_file = self._title_to_file(title)
        return repo_file in self._changectx()

    def __iter__(self):
        return self.all_pages()

    def _get_parents(self, filename, parent_rev):
        if parent_rev is None:
            return 'tip', None
        try:
            filetip = self._changectx()[filename]
        except mercurial.revlog.LookupError:
            if parent_rev != -1:
                raise IndexError("no such parent revision %r" % parent_rev)
            return ('tip', None)
        last_rev = filetip.filerev()
        if parent_rev > last_rev:
            raise IndexError("no such parent revision %r" % parent_rev)
        if parent_rev == last_rev:
            return ('tip', None)
        return parent_rev, last_rev

    def _merge(self, repo_file, parent, other, data):
        filetip = self._changectx()[repo_file]
        parent_data = filetip.filectx(parent).data()
        other_data = filetip.filectx(other).data()
        return merge_func(parent_data, other_data, data)


    def save_data(self, title, data, author=None, comment=None, parent_rev=None):
        """Save a new revision of the page. If the data is None, deletes it."""

        self.reopen() # Make sure we are at the tip.
        _ = self._
        user = (author or _(u'anon')).encode('utf-8')
        text = (comment or _(u'comment')).encode('utf-8')
        repo_file = self._title_to_file(title)
        parent, other = self._get_parents(repo_file, parent_rev)
        if data is None:
            if title not in self:
                raise error.ForbiddenErr()
        else:
            if other is not None:
                try:
                    data = self._merge(repo_file, parent, other, data)
                except ValueError:
                    text = _(u'failed merge of edit conflict').encode('utf-8')
        def filectxfn(repo, memctx, path):
            if data is None:
                return _file_deleted()
            return _get_memfilectx(repo, path, data, memctx=memctx)
        ctx = mercurial.context.memctx(
            repo=self.repo,
            parents=(parent, other),
            text=text,
            files=[repo_file],
            filectxfn=filectxfn,
            user=user,
        )
        self.repo.commitctx(ctx)
        self.reopen()

    def delete_page(self, title, author, comment):
        self.save_data(title, None, author, comment)

    def save_text(self, title, text, author=u'', comment=u'', parent=None):
        """Save text as specified page, encoded to charset."""

        data = text.encode(self.charset)
        if self.unix_eol:
            data = data.replace('\r\n', '\n')
        self.save_data(title, data, author, comment, parent)

    def page_text(self, title):
        """Read unicode text of a page."""

        data = self.page_data(title)
        text = unicode(data, self.charset, 'replace')
        return text

    def open_page(self, title):
        """Open the page and return a file-like object with its contents."""
        return StringIO.StringIO(self.page_data(title))

    def page_data(self, title):
        repo_file = self._title_to_file(title)
        try:
            filetip = self._changectx()[repo_file]
        except mercurial.revlog.LookupError:
            raise error.NotFoundErr()
        return filetip.data()

    def page_meta(self, title):
        """Get page's revision, date, last editor and his edit comment."""

        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            raise error.NotFoundErr()
            #return -1, None, u'', u''
        rev = filectx_tip.filerev()
        filectx = filectx_tip.filectx(rev)
        date = _get_datetime(filectx)
        author = unicode(filectx.user(), "utf-8",
                         'replace').split('<')[0].strip()
        comment = unicode(filectx.description(), "utf-8", 'replace')
        return rev, date, author, comment

    def repo_revision(self):
        """Give the latest revision of the repository."""

        return self._changectx().rev()

    def _changectx(self):
        """Get the changectx of the tip."""

        thread_id = thread.get_ident()
        try:
            return self._tips[thread_id]
        except KeyError:
            try:
                # This is for Mercurial 1.0
                tip = self.repo.changectx()
            except TypeError:
                # Mercurial 1.3 (and possibly earlier) needs an argument
                tip = self.repo.changectx('tip')
            self._tips[thread_id] = tip
            return tip

    def _find_filectx(self, title):
        """Find the last revision in which the file existed."""

        repo_file = self._title_to_file(title)
        stack = [self._changectx()]
        while stack:
            changectx = stack.pop()
            if repo_file in changectx:
                return changectx[repo_file]
            if changectx.rev() == 0:
                return None
            for parent in changectx.parents():
                if parent != changectx:
                    stack.append(parent)
        return None

    def page_history(self, title):
        """Iterate over the page's history."""

        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            return
        maxrev = filectx_tip.filerev()
        minrev = 0
        for rev in range(maxrev, minrev - 1, -1):
            filectx = filectx_tip.filectx(rev)
            date = _get_datetime(filectx)
            author = unicode(filectx.user(), "utf-8",
                             'replace').split('<')[0].strip()
            comment = unicode(filectx.description(), "utf-8", 'replace')
            yield rev, date, author, comment

    def page_revision(self, title, rev):
        """Get binary content of the specified revision of the page."""

        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            raise error.NotFoundErr()
        try:
            data = filectx_tip.filectx(rev).data()
        except LookupError:
            raise error.NotFoundErr()
        return data

    def revision_text(self, title, rev):
        """Get unicode text of the specified revision of the page."""

        data = self.page_revision(title, rev)
        text = unicode(data, self.charset, 'replace')
        return text

    def history(self):
        """Iterate over the history of entire wiki."""

        changectx = self._changectx()
        maxrev = changectx.rev()
        minrev = 0
        for wiki_rev in range(maxrev, minrev - 1, -1):
            change = self.repo.changectx(wiki_rev)
            date = _get_datetime(change)
            author = unicode(change.user(), "utf-8",
                             'replace').split('<')[0].strip()
            comment = unicode(change.description(), "utf-8", 'replace')
            for repo_file in change.files():
                if repo_file.startswith(self.repo_prefix):
                    title = self._file_to_title(repo_file)
                    try:
                        rev = change[repo_file].filerev()
                    except mercurial.revlog.LookupError:
                        rev = -1
                    yield title, rev, date, author, comment

    def all_pages(self):
        """Iterate over the titles of all pages in the wiki."""

        for repo_file in self._changectx():
            if (repo_file.startswith(self.repo_prefix) and
                '/' not in repo_file[len(self.repo_prefix):].strip('/')):
                title = self._file_to_title(repo_file)
                if title in self:
                    yield title

    def changed_since(self, rev):
        """
        Return all pages that changed since specified repository revision.
        """

        try:
            last = self.repo.lookup(int(rev))
        except IndexError:
            for page in self.all_pages():
                yield page
            return
        current = self.repo.lookup('tip')
        status = self.repo.status(current, last)
        modified, added, removed, deleted, unknown, ignored, clean = status
        for filename in modified + added + removed + deleted:
            if filename.startswith(self.repo_prefix):
                yield self._file_to_title(filename)


class WikiSubdirectoryStorage(WikiStorage):
    """
    A version of WikiStorage that keeps the subpages in real subdirectories in
    the filesystem. Indexes supported.

    """

    periods_re = re.compile(r'^[.]|(?<=/)[.]')
    slashes_re = re.compile(r'^[/]|(?<=/)[/]')

    # TODO: make them configurable
    index = "Index"

    def _is_directory(self, repo_path):
        """Checks whether the path is a directory in the repository."""

        if not repo_path:
            return True
        return repo_path in self._changectx().dirs()

    def _title_to_file(self, title):
        """
        Modified escaping allowing (some) slashes and spaces.
        If the entry is a directory, use an index file.
        """

        title = unicode(title).strip()
        escaped = werkzeug.url_quote(title, safe='/ ')
        escaped = self.periods_re.sub('%2E', escaped)
        escaped = self.slashes_re.sub('%2F', escaped)
        path = os.path.join(self.repo_prefix, escaped)
        if self._is_directory(path):
            path = os.path.join(path, self.index)
        if page.page_mime(title) == 'text/x-wiki' and self.extension:
            path += self.extension
        return path

    def _file_to_title(self, filepath):
        """If the path points to an index file, use the directory."""

        if os.path.basename(filepath) == self.index:
            filepath = os.path.dirname(filepath)
        return super(WikiSubdirectoryStorage, self)._file_to_title(filepath)

    def save_data(self, title, data, author=u'', comment=u'', parent_rev=None):
        """Save the file and make the subdirectories if needed."""

        _ = self._
        user = (author or _(u'anon')).encode('utf-8')
        text = (comment or _(u'comment')).encode('utf-8')
        repo_file = self._title_to_file(title)
        files = [repo_file]
        dir_path = None
        new_dir_path = None
        if os.path.basename(repo_file) != self.index:
            # Move a colliding file out of the way.
            dir_path = os.path.dirname(repo_file)
            while dir_path:
                if dir_path in self._changectx():
                    new_dir_path = os.path.join(dir_path, self.index)
                    files.extend([dir_path, new_dir_path])
                    dir_data = self._changectx()[dir_path].data()
                    break
                dir_path = os.path.dirname(dir_path)
        parent, other = self._get_parents(repo_file, parent_rev)
        if data is None:
            if title not in self:
                raise error.NotFoundErr()
        else:
            if other is not None:
                try:
                    data = self._merge(repo_file, parent, other, data)
                except ValueError:
                    text = _(u'failed merge of edit conflict').encode('utf-8')
        def filectxfn(repo, memctx, path):
            if data is None or path == dir_path:
                return _file_deleted()
            if path == new_dir_path:
                return _get_memfilectx(repo, path, dir_data, memctx=memctx, copied=dir_path)
            return _get_memfilectx(repo, path, data, memctx=memctx)
        ctx = mercurial.context.memctx(
            repo=self.repo,
            parents=(parent, other),
            text=text,
            files=files,
            filectxfn=filectxfn,
            user=user,
        )
        self.repo.commitctx(ctx)
        self._tips = {}

    def all_pages(self):
        """Iterate over the titles of all pages in the wiki."""

        for repo_file in self._changectx():
            if repo_file.startswith(self.repo_prefix):
                title = self._file_to_title(repo_file)
                if title in self:
                    yield title
