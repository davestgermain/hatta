#!/usr/bin/python
# -*- coding: utf-8 -*-

import datetime
import errno
import os
import re
import tempfile
import thread
import werkzeug

# Note: we have to set these before importing Mercurial
os.environ['HGENCODING'] = 'utf-8'
os.environ['HGMERGE'] = "internal:merge"

import mercurial.commands
import mercurial.hg
import mercurial.hgweb
import mercurial.merge
import mercurial.revlog
import mercurial.ui
import mercurial.util

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

    def reopen(self):
        """Close and reopen the repo, to make sure we are up to date."""

        self._repos = {}

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

    def _check_path(self, path):
        """
        Ensure that the path is within allowed bounds.
        """

        _ = self._
        abspath = os.path.abspath(path)
        if os.path.islink(path) or os.path.isdir(path):
            raise error.ForbiddenErr(
                _(u"Can't use symbolic links or directories as pages"))
        if not abspath.startswith(self.path):
            raise error.ForbiddenErr(
                _(u"Can't read or write outside of the pages repository"))

    def _file_path(self, title):
        return os.path.join(self.repo_path, self._title_to_file(title))

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
        if title:
            file_path = self._file_path(title)
            return os.path.isfile(file_path) and not os.path.islink(file_path)

    def __iter__(self):
        return self.all_pages()

    def merge_changes(self, changectx, repo_file, text, user, parent):
        """Commits and merges conflicting changes in the repository."""

        _ = self._
        tip_node = changectx.node()
        filectx = changectx[repo_file].filectx(parent)
        parent_node = filectx.changectx().node()

        self.repo.dirstate.setparents(parent_node)
        node = self._commit([repo_file], text, user)

        partial = lambda filename: repo_file == filename
        try:
            mercurial.merge.update(self.repo, tip_node, True, True, partial)
            msg = _(u'merge of edit conflict')
        except mercurial.util.Abort:
            msg = _(u'failed merge of edit conflict')
        self.repo.dirstate.setparents(tip_node, node)
        # Mercurial 1.1 and later need updating the merge state
        try:
            mergestate = mercurial.merge.mergestate
        except AttributeError:
            pass
        else:
            state = mergestate(self.repo)
            try:
                state.mark(repo_file, "r")
            except KeyError:
                # There were no conflicts to mark
                pass
            else:
                # Mercurial 1.7+ needs a commit
                try:
                    commit = state.commit
                except AttributeError:
                    pass
                else:
                    commit()
        return msg

    @locked_repo
    def save_file(self, title, file_name, author=u'', comment=u'',
                  parent=None):
        """Save an existing file as specified page."""

        _ = self._
        user = author.encode('utf-8') or _(u'anon').encode('utf-8')
        text = comment.encode('utf-8') or _(u'comment').encode('utf-8')
        repo_file = self._title_to_file(title)
        file_path = self._file_path(title)
        self._check_path(file_path)
        try:
            mercurial.util.rename(file_name, file_path)
        except OSError, e:
            if e.errno == errno.ENAMETOOLONG:
                # "File name too long"
                raise error.RequestURITooLarge()
            else:
                raise
        changectx = self._changectx()
        try:
            # Mercurial 1.5 and earlier have .add() on the repo
            add = self.repo.add
        except AttributeError:
            # Mercurial 1.6
            add = self.repo[None].add
        try:
            filectx_tip = changectx[repo_file]
            current_page_rev = filectx_tip.filerev()
        except mercurial.revlog.LookupError:
            add([repo_file])
            current_page_rev = -1
        if parent is not None and current_page_rev != parent:
            msg = self.merge_changes(changectx, repo_file, text, user, parent)
            user = '<wiki>'
            text = msg.encode('utf-8')
        self._commit([repo_file], text, user)

    def _commit(self, files, text, user):
        try:
            return self.repo.commit(files=files, text=text, user=user,
                                    force=True, empty_ok=True)
        except TypeError:
            # Mercurial 1.3 doesn't accept empty_ok or files parameter
            match = mercurial.match.exact(self.repo_path, '', list(files))
            return self.repo.commit(match=match, text=text, user=user,
                                    force=True)

    def save_data(self, title, data, author=u'', comment=u'', parent=None):
        """Save data as specified page."""

        try:
            temp_path = tempfile.mkdtemp(dir=self.path)
            file_path = os.path.join(temp_path, 'saved')
            f = open(file_path, "wb")
            f.write(data)
            f.close()
            self.save_file(title, file_path, author, comment, parent)
        finally:
            try:
                os.unlink(file_path)
            except OSError:
                pass
            try:
                os.rmdir(temp_path)
            except OSError:
                pass

    def save_text(self, title, text, author=u'', comment=u'', parent=None):
        """Save text as specified page, encoded to charset."""

        data = text.encode(self.charset)
        if self.unix_eol:
            data = data.replace('\r\n', '\n')
        self.save_data(title, data, author, comment, parent)

    def page_text(self, title):
        """Read unicode text of a page."""

        data = self.open_page(title).read()
        text = unicode(data, self.charset, 'replace')
        return text

    def page_lines(self, page):
        for data in page.xreadlines():
            yield unicode(data, self.charset, 'replace')

    @locked_repo
    def delete_page(self, title, author=u'', comment=u''):
        user = author.encode('utf-8') or 'anon'
        text = comment.encode('utf-8') or 'deleted'
        repo_file = self._title_to_file(title)
        file_path = self._file_path(title)
        self._check_path(file_path)
        try:
            # Mercurial 1.5 and earlier have .remove() on the repo
            remove = self.repo.remove
        except AttributeError:
            # Mercurial 1.6 and later
            try:
                remove = self.repo[None].remove
            except AttributeError:
                # Mercurial 1.9 and later
                remove = self.repo[None].forget
        try:
            os.unlink(file_path)
        except OSError:
            pass
        remove([repo_file])
        self._commit([repo_file], text, user)

    def open_page(self, title):
        """Open the page and return a file-like object with its contents."""

        file_path = self._file_path(title)
        self._check_path(file_path)
        try:
            return open(file_path, "rb")
        except IOError:
            raise error.NotFoundErr()

    def page_file_meta(self, title):
        """Get page's inode number, size and last modification time."""

        try:
            (st_mode, st_ino, st_dev, st_nlink, st_uid, st_gid, st_size,
             st_atime, st_mtime, st_ctime) = os.stat(self._file_path(title))
        except OSError:
            return 0, 0, 0
        return st_ino, st_size, st_mtime

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

        try:
            # This is for Mercurial 1.0
            return self.repo.changectx()
        except TypeError:
            # Mercurial 1.3 (and possibly earlier) needs an argument
            return self.repo.changectx('tip')

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
        except IndexError:
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

        for filename in os.listdir(self.path):
            file_path = os.path.join(self.path, filename)
            file_repopath = os.path.join(self.repo_prefix, filename)
            if (os.path.isfile(file_path)
                and not os.path.islink(file_path)
                and not filename.startswith('.')):
                yield self._file_to_title(file_repopath)

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
        if os.path.isdir(os.path.join(self.repo_path, path)):
            path = os.path.join(path, self.index)
        if page.page_mime(title) == 'text/x-wiki' and self.extension:
            path += self.extension
        return path

    def _file_to_title(self, filepath):
        """If the path points to an index file, use the directory."""

        if os.path.basename(filepath) == self.index:
            filepath = os.path.dirname(filepath)
        return super(WikiSubdirectoryStorage, self)._file_to_title(filepath)

    def turn_into_subdirectory(self, path):
        """Turn a single-file page into an index page inside a subdirectory."""

        _ = self._
        self._check_path(path)
        dir_path = os.path.dirname(path)
        if not os.path.isdir(dir_path):
            self.turn_into_subdirectory(dir_path)
        if not os.path.exists(path):
            os.mkdir(path)
            return
        try:
            temp_dir = tempfile.mkdtemp(dir=self.path)
            temp_path = os.path.join(temp_dir, 'saved')
            mercurial.commands.rename(self.ui, self.repo, path, temp_path)
            os.makedirs(path)
            index_path = os.path.join(path, self.index)
            mercurial.commands.rename(self.ui, self.repo, temp_path,
                                      index_path)
        finally:
            try:
                os.rmdir(temp_dir)
            except OSError:
                pass
        def repo_path(path):
            return path[len(self.repo_path)+1:]
        files = [repo_path(index_path), repo_path(path)]
        self._commit(files, _(u"made subdirectory page"), "<wiki>")

    @locked_repo
    def save_file(self, title, file_name, author=u'', comment=u'',
                  parent=None):
        """Save the file and make the subdirectories if needed."""

        path = self._file_path(title)
        dir_path = os.path.dirname(path)
        if not os.path.isdir(dir_path):
            self.turn_into_subdirectory(dir_path)
        try:
            os.makedirs(os.path.join(self.repo_path, dir_path))
        except OSError, e:
            if e.errno != errno.EEXIST:
                # "File exists"
                raise
        super(WikiSubdirectoryStorage, self).save_file(title, file_name,
                                                       author, comment, parent)

    @locked_repo
    def delete_page(self, title, author=u'', comment=u''):
        """
        Remove empty directories after deleting a page.

        Note that Mercurial doesn't track directories, so we don't have to
        commit after removing empty directories.
        """

        super(WikiSubdirectoryStorage, self).delete_page(title, author,
                                                         comment)
        file_path = self._file_path(title)
        self._check_path(file_path)
        dir_path = os.path.dirname(file_path)
        if dir_path != self.repo_path:
            try:
                os.removedirs(dir_path)
            except OSError, e:
                if e.errno != errno.ENOTEMPTY:
                    # "Directory not empty"
                    raise

    def all_pages(self):
        """
        Iterate over the titles of all pages in the wiki.
        Include subdirectories but skip over index.
        """

        for (dirpath, dirnames, filenames) in os.walk(self.path):
            path = dirpath[len(self.path) + 1:]
            for name in filenames:
                filepath = os.path.join(dirpath, name)
                repopath = os.path.join(self.repo_prefix, path, name)
                if (os.path.isfile(filepath)
                    and not name.startswith('.')):
                    yield self._file_to_title(repopath)
