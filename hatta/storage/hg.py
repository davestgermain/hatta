#!/usr/bin/python
# -*- coding: utf-8 -*-

import datetime
import os
import re
from werkzeug.urls import url_quote, url_unquote
import io

# Note: we have to set these before importing Mercurial
os.environ['HGENCODING'] = 'utf-8'

import mercurial.hg
import mercurial.node
import mercurial.ui

from hatta import error
from hatta import page

from .base import BaseWikiStorage, Revision, merge_func


class StorageError(Exception):
    """Thrown when there are problems with configuration of storage."""


class HgRevision(Revision):
    pass


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


def _get_memfilectx(repo, path, data, islink=False, isexec=False, copied=None, memctx=None):
    return mercurial.context.memfilectx(
        repo=repo,
        changectx=memctx,
        path=path,
        data=data,
        islink=islink,
        isexec=isexec,
        copysource=copied,
    )


def _get_datetime(filectx):
    """
    Create a datetime object for the changeset's cretion time, taking into
    account the timezones.
    """

    timestamp, offset = filectx.date()
    date = datetime.datetime.fromtimestamp(timestamp + offset)
    return date


class WikiStorage(BaseWikiStorage):
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
        super(WikiStorage, self).__init__(charset=charset, _=_, unix_eol=unix_eol, extension=extension)
        self.path = os.path.abspath(path)
        if not os.path.exists(self.path):
            os.makedirs(self.path)
        ui = mercurial.ui.ui()
        ui.quiet = True
        ui._report_untrusted = False
        ui.setconfig(b'ui', b'interactive', False)
        self.ui = ui

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
            mercurial.hg.repository(self.ui, self.repo_path.encode('utf8'), create=True)
        self.reopen()

    def get_cache_path(self):
        return os.path.join(self.repo_path, '.hg', 'hatta', 'cache')

    def get_index_path(self):
        return os.path.join(self.repo_path, '.hg', 'hatta', 'search')

    def open_repo(self):
        return mercurial.hg.repository(self.ui, self.repo_path.encode('utf8'))

    def get_tip(self):
        """Get the changectx of the tip."""
        return self.repo[b'tip']

    def _file_to_title(self, filepath):
        _ = self._
        if not filepath.startswith(self.repo_prefix):
            raise error.ForbiddenErr(
                _("Can't read or write outside of the pages repository"))
        sep = os.path.sep
        name = filepath[len(self.repo_prefix):].strip(sep)
        # Un-escape special windows filenames and dot files
        if name.startswith('_') and len(name) > 1:
            name = name[1:]
        if self.extension and name.endswith(self.extension):
            name = name[:-len(self.extension)]
        return url_unquote(name)

    def __contains__(self, title):
        repo_file = self._title_to_file(title).encode('utf8')
        return repo_file in self.tip

    def __iter__(self):
        return self.all_pages()

    def _get_parents(self, filename, parent_rev):
        if parent_rev is None:
            return b'tip', None
        parent_rev = int(parent_rev)
        try:
            filetip = self.tip[filename]
        except mercurial.error.ManifestLookupError:
            return (b'tip', None)
        last_rev = filetip.filerev()
        if parent_rev > last_rev:
            raise IndexError("no such parent revision %r" % parent_rev)
        if parent_rev == last_rev:
            return (b'tip', None)
        return parent_rev, last_rev

    def _merge(self, repo_file, parent, other, data):
        filetip = self.tip[repo_file]
        parent_data = filetip.filectx(parent)
        other_data = filetip.filectx(other)
        return merge_func(parent_data, other_data, data)

    def _commit(self, parent, other, text, files, filectxfn, user):
        ctx = mercurial.context.memctx(
            repo=self.repo,
            parents=(parent, other),
            text=text,
            files=files,
            filectxfn=filectxfn,
            user=user,
        )
        ret = self.repo.commitctx(ctx)
        if self.repo.changelog.hasnode(ret):
            self.repo.hook("commit", node=mercurial.node.hex(ret),
                           parent1=parent, parent2=other)

    def save_data(self, title, data, author=None, comment=None, parent_rev=None):
        """Save a new revision of the page. If the data is None, deletes it."""

        self.reopen() # Make sure we are at the tip.
        _ = self._
        user = (author or _('anon')).encode('utf-8')
        text = (comment or _('comment')).encode('utf-8')
        repo_file = self._title_to_file(title).encode('utf8')

        parent, other = self._get_parents(repo_file, parent_rev)
        if data is None:
            if title not in self:
                raise error.ForbiddenErr()
        else:
            if other is not None:
                try:
                    data = self._merge(repo_file, parent, other, data)
                except ValueError:
                    text = _('failed merge of edit conflict').encode('utf-8')
        def filectxfn(repo, memctx, path):
            if data is None:
                return None
            return _get_memfilectx(repo, path, data, memctx=memctx)

        self._commit(parent, other, text, [repo_file], filectxfn, user)
        self.reopen()

    def delete_page(self, title, author, comment):
        self.save_data(title, None, author, comment)

    def save_text(self, title, text, author='', comment='', parent=None):
        """Save text as specified page, encoded to charset."""

        data = text.encode(self.charset)
        if self.unix_eol:
            data = data.replace('\r\n', '\n')
        self.save_data(title, data, author, comment, parent)

    def get_revision(self, title, rev=None):
        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            raise error.NotFoundErr()
        if rev is None:
            rev = filectx_tip.filerev()
        else:
            rev = int(rev)
        filectx = filectx_tip.filectx(rev)
        try:
            data = filectx.data()
        except mercurial.error.LookupError:
            raise error.NotFoundErr()
        date = _get_datetime(filectx)
        author = str(filectx.user(), "utf-8",
                         'replace').split('<')[0].strip()
        comment = str(filectx.description(), "utf-8", 'replace')

        revision = HgRevision(self, rev=rev, data=data, date=date, author=author, comment=comment, charset=self.charset)
        return revision

    def repo_revision(self):
        """Give the latest revision of the repository."""

        return str(self.tip.rev())

    def _find_filectx(self, title):
        """Find the last revision in which the file existed."""

        repo_file = self._title_to_file(title).encode('utf8')
        stack = [self.tip]
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
            author = str(filectx.user(), "utf-8",
                             'replace').split('<')[0].strip()
            comment = str(filectx.description(), "utf-8", 'replace')
            yield {
                'title': title,
                'rev': str(rev),
                'parent': str(rev - 1) if rev else None,
                'date': date,
                'author': author,
                'comment': comment
            }

    def history(self):
        """Iterate over the history of entire wiki."""

        changectx = self.tip
        maxrev = changectx.rev()
        minrev = 0
        for wiki_rev in range(maxrev, minrev - 1, -1):
            change = self.repo[wiki_rev]
            date = _get_datetime(change)
            author = str(change.user(), "utf-8",
                             'replace').split('<')[0].strip()
            comment = str(change.description(), "utf-8", 'replace')
            for repo_file in change.files():
                repo_file_str = repo_file.decode('utf8')
                if repo_file_str.startswith(self.repo_prefix):
                    title = self._file_to_title(repo_file_str)
                    try:
                        rev = change[repo_file].filerev()
                    except mercurial.error.LookupError:
                        rev = -1
                    yield {
                        'title': title,
                        'rev': str(rev),
                        'date': date,
                        'author': author,
                        'comment': comment,
                        'parent': str(rev - 1) if rev else None,
                    }

    def all_pages(self):
        """Iterate over the titles of all pages in the wiki."""

        sep = os.path.sep
        for repo_file in self.tip:
            repo_file = repo_file.decode('utf8')
            if (repo_file.startswith(self.repo_prefix) and
                sep not in repo_file[len(self.repo_prefix):].strip(sep)):
                title = self._file_to_title(repo_file)
                if title in self:
                    yield title

    def changed_since(self, rev):
        """
        Return all pages that changed since specified repository revision.
        """

        try:
            last = self.repo.lookup(str(rev or 0).encode('utf8'))
        except mercurial.error.RepoLookupError:
            for page in self.all_pages():
                yield page
            return
        current = self.repo.lookup(b'tip')
        status = self.repo.status(current, last)
        modified, added, removed, deleted, unknown, ignored, clean = status
        for filename in modified + added + removed + deleted:
            filename = filename.decode('utf8')
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
    index = b"Index"

    def _is_directory(self, repo_path):
        """Checks whether the path is a directory in the repository."""

        if not repo_path:
            return True
        return repo_path.encode('utf8') in self.tip.dirs()

    def _title_to_file(self, title):
        """
        Modified escaping allowing (some) slashes and spaces.
        If the entry is a directory, use an index file.
        """

        title = str(title).strip()
        escaped = url_quote(title, safe='/ ')
        escaped = self.periods_re.sub('%2E', escaped)
        escaped = self.slashes_re.sub('%2F', escaped)
        path = os.path.join(self.repo_prefix, escaped)

        if self._is_directory(path):
            path = os.path.join(path, self.index.decode('utf8'))
        if page.page_mime(title) == 'text/x-wiki' and self.extension:
            path += self.extension
        return path

    def _file_to_title(self, filepath):
        """If the path points to an index file, use the directory."""

        if os.path.basename(filepath) == self.index:
            filepath = os.path.dirname(filepath)
        return super(WikiSubdirectoryStorage, self)._file_to_title(filepath)

    def save_data(self, title, data, author='', comment='', parent_rev=None):
        """Save the file and make the subdirectories if needed."""

        _ = self._
        user = (author or _('anon')).encode('utf-8')
        text = (comment or _('comment')).encode('utf-8')
        repo_file = self._title_to_file(title).encode('utf8')

        files = [repo_file]
        dir_path = None
        new_dir_path = None

        if os.path.basename(repo_file) != self.index:
            # Move a colliding file out of the way.
            dir_path = os.path.dirname(repo_file)
            while dir_path:
                if dir_path in self.tip:
                    new_dir_path = os.path.join(dir_path, self.index)
                    files.extend([dir_path, new_dir_path])
                    dir_data = self.tip[dir_path].data()
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
                    text = _('failed merge of edit conflict').encode('utf-8')
        def filectxfn(repo, memctx, path):
            if data is None or path == dir_path:
                return None
            if path == new_dir_path:
                return _get_memfilectx(repo, path, dir_data, memctx=memctx, copied=dir_path)
            return _get_memfilectx(repo, path, data, memctx=memctx)
        self._commit(parent, other, text, files, filectxfn, user)
        self.tip = None

    def all_pages(self):
        """Iterate over the titles of all pages in the wiki."""

        for repo_file in self.tip:
            if repo_file.startswith(self.repo_prefix):
                title = self._file_to_title(repo_file)
                if title in self:
                    yield title
