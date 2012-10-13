#!/usr/bin/python
# -*- coding: utf-8 -*-

import gettext
import os
import sys
import re
import tempfile
import itertools

import werkzeug
import werkzeug.routing
import jinja2

pygments = None
try:
    import pygments
except ImportError:
    pass

import hatta
import storage
import search
import page
import parser
import error
import data

import mercurial  # import it after storage!


class WikiResponse(werkzeug.BaseResponse, werkzeug.ETagResponseMixin,
                   werkzeug.CommonResponseDescriptorsMixin):
    """A typical HTTP response class made out of Werkzeug's mixins."""

    def make_conditional(self, request):
        ret = super(WikiResponse, self).make_conditional(request)
        # Remove all headers if it's 304, according to
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.3.5
        if self.status.startswith('304'):
            self.response = []
            try:
                del self.content_type
            except (AttributeError, KeyError, IndexError):
                pass
            try:
                del self.content_length
            except (AttributeError, KeyError, IndexError):
                pass
            try:
                del self.headers['Content-length']
            except (AttributeError, KeyError, IndexError):
                pass
            try:
                del self.headers['Content-type']
            except (AttributeError, KeyError, IndexError):
                pass
        return ret


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


class WikiTitleConverter(werkzeug.routing.PathConverter):
    """Behaves like the path converter, but doesn't match the "+ pages"."""

    def to_url(self, value):
        return werkzeug.url_quote(value.strip(), self.map.charset, safe="/")

    regex = '([^+%]|%[^2]|%2[^Bb]).*'


class WikiAllConverter(werkzeug.routing.BaseConverter):
    """Matches everything."""

    regex = '.*'


class URL(object):
    """A decorator for marking methods as endpoints for URLs."""

    urls = []

    def __init__(self, url, methods=None):
        """Create a decorator with specified parameters."""

        self.url = url
        self.methods = methods or ['GET', 'HEAD']

    def __call__(self, func):
        """The actual decorator only records the data."""

        self.urls.append((func.__name__, self.url, self.methods))
        return func

    @classmethod
    def rules(cls, app):
        """Returns the routing rules, using app's bound methods."""

        for name, url, methods in cls.urls:
            func = getattr(app, name, None)
            if not callable(func):
                continue
            yield werkzeug.routing.Rule(url, endpoint=func, methods=methods)


class Wiki(object):
    """
    The main class of the wiki, handling initialization of the whole
    application and most of the logic.
    """
    storage_class = storage.WikiStorage
    index_class = search.WikiSearch
    filename_map = page.filename_map
    mime_map = page.mime_map
    icon = data.icon
    scripts = data.scripts
    style = data.style

    def __init__(self, config):
        if config.get_bool('show_version', False):
            sys.stdout.write("Hatta %s\n" % hatta.__version__)
            sys.exit()
        self.dead = False
        self.config = config

        self.language = config.get('language', None)
        if self.language is not None:
            try:
                translation = gettext.translation('hatta', 'locale',
                                        languages=[self.language])

            except IOError:
                translation = gettext.translation('hatta', fallback=True,
                                        languages=[self.language])
        else:
            translation = gettext.translation('hatta', fallback=True)
        self.gettext = translation.ugettext
        self.template_env = jinja2.Environment(
                            extensions=['jinja2.ext.i18n'],
                            loader=jinja2.PackageLoader('hatta', 'templates'),
                            )
        self.template_env.autoescape = True
        self.template_env.install_gettext_translations(translation, True)
        self.path = os.path.abspath(config.get('pages_path', 'docs'))
        self.repo_path = config.get('repo_path', None)
        self.page_charset = config.get('page_charset', 'utf-8')
        self.menu_page = self.config.get('menu_page', u'Menu')
        self.front_page = self.config.get('front_page', u'Home')
        self.logo_page = self.config.get('logo_page', u'logo.png')
        self.locked_page = self.config.get('locked_page', u'Locked')
        self.site_name = self.config.get('site_name', u'Hatta Wiki')
        self.read_only = self.config.get_bool('read_only', False)
        self.icon_page = self.config.get('icon_page', None)
        self.alias_page = self.config.get('alias_page', 'Alias')
        self.pygments_style = self.config.get('pygments_style', 'tango')
        self.subdirectories = self.config.get_bool('subdirectories', False)
        self.extension = self.config.get('extension', None)
        self.unix_eol = self.config.get_bool('unix_eol', False)
        if self.subdirectories:
            self.storage = storage.WikiSubdirectoryStorage(self.path,
                self.page_charset, self.gettext, self.unix_eol, self.extension,
                self.repo_path)
        else:
            self.storage = self.storage_class(self.path, self.page_charset,
                self.gettext, self.unix_eol, self.extension,
                self.repo_path)
        self.repo_path = self.storage.repo_path
        self.cache = os.path.abspath(config.get('cache_path',
                os.path.join(self.repo_path, '.hg', 'hatta', 'cache')))
        self.index = self.index_class(self.cache, self.language, self.storage)
        self.index.update(self)
        self.url_rules = URL.rules(self)
        self.url_map = werkzeug.routing.Map(self.url_rules, converters={
            'title': WikiTitleConverter,
            'all': WikiAllConverter,
        })

    def add_url_rule(self, rule):
        """Let plugins add additional url rules."""

        self.url_rules.append(rule)
        self.url_map = werkzeug.routing.Map(self.url_rules, converters={
            'title': WikiTitleConverter,
            'all': WikiAllConverter,
        })

    def get_page(self, request, title):
        """Creates a page object based on page's mime type"""

        if title:
            try:
                page_class, mime = self.filename_map[title]
            except KeyError:
                mime = page.page_mime(title)
                major, minor = mime.split('/', 1)
                try:
                    page_class = self.mime_map[mime]
                except KeyError:
                    try:
                        plus_pos = minor.find('+')
                        if plus_pos > 0:
                            minor_base = minor[plus_pos:]
                        else:
                            minor_base = ''
                        base_mime = '/'.join([major, minor_base])
                        page_class = self.mime_map[base_mime]
                    except KeyError:
                        try:
                            page_class = self.mime_map[major]
                        except KeyError:
                            page_class = self.mime_map['']
        else:
            page_class = page.WikiPageSpecial
            mime = ''
        return page_class(self, request, title, mime)

    def response(self, request, title, content, etag='', mime='text/html',
                 rev=None, size=None):
        """Create a WikiResponse for a page."""

        response = WikiResponse(content, mimetype=mime)
        if rev is None:
            inode, _size, mtime = self.storage.page_file_meta(title)
            response.set_etag(u'%s/%s/%d-%d' % (etag,
                                                werkzeug.url_quote(title),
                                                inode, mtime))
            if size == -1:
                size = _size
        else:
            response.set_etag(u'%s/%s/%s' % (etag, werkzeug.url_quote(title),
                                             rev))
        if size:
            response.content_length = size
        response.make_conditional(request)
        return response

    def _check_lock(self, title):
        _ = self.gettext
        restricted_pages = [
            'scripts.js',
            'robots.txt',
        ]
        if self.read_only:
            raise error.ForbiddenErr(_(u"This site is read-only."))
        if title in restricted_pages:
            raise error.ForbiddenErr(_(u"""Can't edit this page.
It can only be edited by the site admin directly on the disk."""))
        if title in self.index.page_links(self.locked_page):
            raise error.ForbiddenErr(_(u"This page is locked."))

    def _serve_default(self, request, title, content, mime):
        """Some pages have their default content."""

        if title in self.storage:
            return self.download(request, title)
        response = WikiResponse(content, mimetype=mime)
        response.set_etag('/%s/-1' % title)
        response.make_conditional(request)
        return response

    @URL('/<title:title>')
    @URL('/')
    def view(self, request, title=None):
        if title is None:
            title = self.front_page
        page = self.get_page(request, title)
        try:
            content = page.view_content()
        except error.NotFoundErr:
            url = request.get_url(title, self.edit, external=True)
            return werkzeug.routing.redirect(url, code=303)
        html = page.template("page.html", content=content)
        dependencies = page.dependencies()
        etag = '/(%s)' % u','.join(dependencies)
        return self.response(request, title, html, etag=etag)

    @URL('/+history/<title:title>/<int:rev>')
    def revision(self, request, title, rev):
        _ = self.gettext
        text = self.storage.revision_text(title, rev)
        link = werkzeug.html.a(werkzeug.html(title),
                               href=request.get_url(title))
        content = [
            werkzeug.html.p(
                werkzeug.html(
                    _(u'Content of revision %(rev)d of page %(title)s:'))
                % {'rev': rev, 'title': link}),
            werkzeug.html.pre(werkzeug.html(text)),
        ]
        special_title = _(u'Revision of "%(title)s"') % {'title': title}
        page = self.get_page(request, title)
        html = page.template('page_special.html', content=content,
                             special_title=special_title)
        response = self.response(request, title, html, rev=rev, etag='/old')
        return response

    @URL('/+version/')
    @URL('/+version/<title:title>')
    def version(self, request, title=None):
        if title is None:
            version = self.storage.repo_revision()
        else:
            try:
                version, x, x, x = self.storage.page_history(title).next()
            except StopIteration:
                version = 0
        return WikiResponse('%d' % version, mimetype="text/plain")

    @URL('/+edit/<title:title>', methods=['POST'])
    def save(self, request, title):
        _ = self.gettext
        self._check_lock(title)
        url = request.get_url(title)
        if request.form.get('cancel'):
            if title not in self.storage:
                url = request.get_url(self.front_page)
        if request.form.get('preview'):
            text = request.form.get("text")
            if text is not None:
                lines = text.split('\n')
            else:
                lines = [werkzeug.html.p(werkzeug.html(
                    _(u'No preview for binaries.')))]
            return self.edit(request, title, preview=lines)
        elif request.form.get('save'):
            comment = request.form.get("comment", "")
            author = request.get_author()
            text = request.form.get("text")
            try:
                parent = int(request.form.get("parent"))
            except (ValueError, TypeError):
                parent = None
            self.storage.reopen()
            self.index.update(self)
            page = self.get_page(request, title)
            if text is not None:
                if title == self.locked_page:
                    for link, label in page.extract_links(text):
                        if title == link:
                            raise error.ForbiddenErr(
                                _(u"This page is locked."))
                if u'href="' in comment or u'http:' in comment:
                    raise error.ForbiddenErr()
                if text.strip() == '':
                    self.storage.delete_page(title, author, comment)
                    url = request.get_url(self.front_page)
                else:
                    self.storage.save_text(title, text, author, comment,
                                           parent)
            else:
                text = u''
                upload = request.files['data']
                f = upload.stream
                if f is not None and upload.filename is not None:
                    try:
                        self.storage.save_file(title, f.tmpname, author,
                                               comment, parent)
                    except AttributeError:
                        self.storage.save_data(title, f.read(), author,
                                               comment, parent)
                else:
                    self.storage.delete_page(title, author, comment)
                    url = request.get_url(self.front_page)
            self.index.update_page(page, title, text=text)
        response = werkzeug.routing.redirect(url, code=303)
        response.set_cookie('author',
                            werkzeug.url_quote(request.get_author()),
                            max_age=604800)
        return response

    @URL('/+edit/<title:title>', methods=['GET'])
    def edit(self, request, title, preview=None):
        self._check_lock(title)
        exists = title in self.storage
        if exists:
            self.storage.reopen()
        page = self.get_page(request, title)
        html = page.render_editor(preview)
        if not exists:
            response = WikiResponse(html, mimetype="text/html",
                                     status='404 Not found')

        elif preview:
            response = WikiResponse(html, mimetype="text/html")
        else:
            response = self.response(request, title, html, '/edit')
        response.headers.add('Cache-Control', 'no-cache')
        return response

    @URL('/+feed/atom')
    @URL('/+feed/rss')
    def atom(self, request):
        _ = self.gettext
        feed = werkzeug.contrib.atom.AtomFeed(self.site_name,
            feed_url=request.url,
            url=request.adapter.build(self.view, force_external=True),
            subtitle=_(u'Track the most recent changes to the wiki '
                       u'in this feed.'))
        history = itertools.islice(self.storage.history(), None, 10, None)
        unique_titles = set()
        for title, rev, date, author, comment in history:
            if title in unique_titles:
                continue
            unique_titles.add(title)
            if rev > 0:
                url = request.adapter.build(self.diff, {
                    'title': title,
                    'from_rev': rev - 1,
                    'to_rev': rev,
                }, force_external=True)
            else:
                url = request.adapter.build(self.revision, {
                    'title': title,
                    'rev': rev,
                }, force_external=True)
            feed.add(title, comment, content_type="text", author=author,
                     url=url, updated=date)
        rev = self.storage.repo_revision()
        response = self.response(request, 'atom', feed.generate(), '/+feed',
                                 'application/xml', rev)
        response.make_conditional(request)
        return response

    @URL('/+download/<title:title>')
    def download(self, request, title):
        """Serve the raw content of a page directly from disk."""

        mime = page.page_mime(title)
        if mime == 'text/x-wiki':
            mime = 'text/plain'
        try:
            wrap_file = werkzeug.wrap_file
        except AttributeError:
            wrap_file = lambda x, y: y
        f = wrap_file(request.environ, self.storage.open_page(title))
        response = self.response(request, title, f, '/download', mime, size=-1)
        response.direct_passthrough = True
        return response

    @URL('/+render/<title:title>')
    def render(self, request, title):
        """Serve a thumbnail or otherwise rendered content."""

        def file_time_and_size(file_path):
            """Get file's modification timestamp and its size."""

            try:
                (st_mode, st_ino, st_dev, st_nlink, st_uid, st_gid, st_size,
                 st_atime, st_mtime, st_ctime) = os.stat(file_path)
            except OSError:
                st_mtime = 0
                st_size = None
            return st_mtime, st_size

        def rm_temp_dir(dir_path):
            """Delete the directory with subdirectories."""

            for root, dirs, files in os.walk(dir_path, topdown=False):
                for name in files:
                    try:
                        os.remove(os.path.join(root, name))
                    except OSError:
                        pass
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except OSError:
                        pass
            try:
                os.rmdir(dir_path)
            except OSError:
                pass

        page = self.get_page(request, title)
        try:
            cache_filename, cache_mime = page.render_mime()
            render = page.render_cache
        except (AttributeError, NotImplementedError):
            return self.download(request, title)

        cache_dir = os.path.join(self.cache, 'render',
                                  werkzeug.url_quote(title, safe=''))
        cache_file = os.path.join(cache_dir, cache_filename)
        page_inode, page_size, page_mtime = self.storage.page_file_meta(title)
        cache_mtime, cache_size = file_time_and_size(cache_file)
        if page_mtime > cache_mtime:
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)
            try:
                temp_dir = tempfile.mkdtemp(dir=cache_dir)
                result_file = render(temp_dir)
                mercurial.util.rename(result_file, cache_file)
            finally:
                rm_temp_dir(temp_dir)
        try:
            wrap_file = werkzeug.wrap_file
        except AttributeError:
            wrap_file = lambda x, y: y
        f = wrap_file(request.environ, open(cache_file))
        response = self.response(request, title, f, '/render', cache_mime,
                                 size=cache_size)
        response.direct_passthrough = True
        return response

    @URL('/+undo/<title:title>', methods=['POST'])
    def undo(self, request, title):
        """Revert a change to a page."""

        _ = self.gettext
        self._check_lock(title)
        rev = None
        for key in request.form:
            try:
                rev = int(key)
            except ValueError:
                pass
        author = request.get_author()
        if rev is not None:
            try:
                parent = int(request.form.get("parent"))
            except (ValueError, TypeError):
                parent = None
            self.storage.reopen()
            self.index.update(self)
            if rev == 0:
                comment = _(u'Delete page %(title)s') % {'title': title}
                data = ''
                self.storage.delete_page(title, author, comment)
            else:
                comment = _(u'Undo of change %(rev)d of page %(title)s') % {
                    'rev': rev, 'title': title}
                data = self.storage.page_revision(title, rev - 1)
                self.storage.save_data(title, data, author, comment, parent)
            page = self.get_page(request, title)
            self.index.update_page(page, title, data=data)
        url = request.adapter.build(self.history, {'title': title},
                                    method='GET', force_external=True)
        return werkzeug.redirect(url, 303)

    @URL('/+history/<title:title>')
    def history(self, request, title):
        """Display history of changes of a page."""

        max_rev = -1
        history = []
        page = self.get_page(request, title)
        for rev, date, author, comment in self.storage.page_history(title):
            if max_rev < rev:
                max_rev = rev
            if rev > 0:
                date_url = request.adapter.build(self.diff, {
                    'title': title, 'from_rev': rev - 1, 'to_rev': rev})
            else:
                date_url = request.adapter.build(self.revision, {
                    'title': title, 'rev': rev})
            history.append((date, date_url, rev, author, comment))
        html = page.template('history.html', history=history,
                             date_html=hatta.page.date_html, parent=max_rev)
        response = self.response(request, title, html, '/history')
        return response

    @URL('/+history/')
    def recent_changes(self, request):
        """Serve the recent changes page."""

        def _changes_list():
            last = {}
            lastrev = {}
            count = 0
            for title, rev, date, author, comment in self.storage.history():
                if (author, comment) == last.get(title, (None, None)):
                    continue
                count += 1
                if count > 100:
                    break
                if rev > 0:
                    date_url = request.adapter.build(self.diff, {
                        'title': title,
                        'from_rev': rev - 1,
                        'to_rev': lastrev.get(title, rev),
                    })
                elif rev == 0:
                    date_url = request.adapter.build(self.revision, {
                        'title': title, 'rev': rev})
                else:
                    date_url = request.adapter.build(self.history, {
                        'title': title})
                last[title] = author, comment
                lastrev[title] = rev

                yield date, date_url, title, author, comment

        page = self.get_page(request, '')
        html = page.template('changes.html', changes=_changes_list(),
                             date_html=hatta.page.date_html)
        response = WikiResponse(html, mimetype='text/html')
        response.set_etag('/history/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    @URL('/+history/<title:title>/<int:from_rev>:<int:to_rev>')
    def diff(self, request, title, from_rev, to_rev):
        """Show the differences between specified revisions."""

        _ = self.gettext
        page = self.get_page(request, title)
        build = request.adapter.build
        from_url = build(self.revision, {'title': title, 'rev': from_rev})
        to_url = build(self.revision, {'title': title, 'rev': to_rev})
        a = werkzeug.html.a
        links = {
            'link1': a(str(from_rev), href=from_url),
            'link2': a(str(to_rev), href=to_url),
            'link': a(werkzeug.html(title), href=request.get_url(title)),
        }
        message = werkzeug.html(_(
            u'Differences between revisions %(link1)s and %(link2)s '
            u'of page %(link)s.')) % links
        diff_content = getattr(page, 'diff_content', None)
        if diff_content:
            from_text = self.storage.revision_text(page.title, from_rev)
            to_text = self.storage.revision_text(page.title, to_rev)
            content = page.diff_content(from_text, to_text, message)
        else:
            content = [werkzeug.html.p(werkzeug.html(
                _(u"Diff not available for this kind of pages.")))]
        special_title = _(u'Diff for "%(title)s"') % {'title': title}
        html = page.template('page_special.html', content=content,
                            special_title=special_title)
        response = WikiResponse(html, mimetype='text/html')
        return response

    @URL('/+index')
    def all_pages(self, request):
        """Show index of all pages in the wiki."""

        _ = self.gettext
        page = self.get_page(request, '')
        html = page.template('list.html',
                             pages=sorted(self.storage.all_pages()),
                             class_='index',
                             message=_(u'Index of all pages'),
                             special_title=_(u'Page Index'))
        response = WikiResponse(html, mimetype='text/html')
        response.set_etag('/+index/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    @URL('/+orphaned')
    def orphaned(self, request):
        """Show all pages that don't have backlinks."""

        _ = self.gettext
        page = self.get_page(request, '')
        html = page.template('list.html',
                             pages=self.index.orphaned_pages(),
                             class_='orphaned',
                             message=_(u'List of pages with no links to them'),
                             special_title=_(u'Orphaned pages'))
        response = WikiResponse(html, mimetype='text/html')
        response.set_etag('/+orphaned/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    @URL('/+wanted')
    def wanted(self, request):
        """Show all pages that don't exist yet, but are linked."""

        def _wanted_pages_list():
            for refs, title in self.index.wanted_pages():
                if not (parser.external_link(title) or title.startswith('+')
                        or title.startswith(':')):
                    yield refs, title

        page = self.get_page(request, '')
        html = page.template('wanted.html', pages=_wanted_pages_list())
        response = WikiResponse(html, mimetype='text/html')
        response.set_etag('/+wanted/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    @URL('/+search', methods=['GET', 'POST'])
    def search(self, request):
        """Serve the search results page."""

        _ = self.gettext

        def search_snippet(title, words):
            """Extract a snippet of text for search results."""

            try:
                text = self.storage.page_text(title)
            except error.NotFoundErr:
                return u''
            regexp = re.compile(u"|".join(re.escape(w) for w in words),
                                re.U | re.I)
            match = regexp.search(text)
            if match is None:
                return u""
            position = match.start()
            min_pos = max(position - 60, 0)
            max_pos = min(position + 60, len(text))
            snippet = werkzeug.escape(text[min_pos:max_pos])
            highlighted = werkzeug.html.b(match.group(0), class_="highlight")
            html = regexp.sub(highlighted, snippet)
            return html

        def page_search(words, page, request):
            """Display the search results."""

            h = werkzeug.html
            self.storage.reopen()
            self.index.update(self)
            result = sorted(self.index.find(words), key=lambda x: -x[0])
            yield werkzeug.html.p(h(_(u'%d page(s) containing all words:')
                                  % len(result)))
            yield u'<ol class="search">'
            for number, (score, title) in enumerate(result):
                yield h.li(h.b(page.wiki_link(title)), u' ', h.i(str(score)),
                           h.div(search_snippet(title, words),
                                 _class="snippet"),
                           id_="search-%d" % (number + 1))
            yield u'</ol>'

        query = request.values.get('q', u'').strip()
        page = self.get_page(request, '')
        if not query:
            url = request.get_url(view=self.all_pages, external=True)
            return werkzeug.routing.redirect(url, code=303)
        words = tuple(self.index.split_text(query))
        if not words:
            words = (query,)
        title = _(u'Searching for "%s"') % u" ".join(words)
        content = page_search(words, page, request)
        html = page.template('page_special.html', content=content,
                             special_title=title)
        return WikiResponse(html, mimetype='text/html')

    @URL('/+search/<title:title>', methods=['GET', 'POST'])
    def backlinks(self, request, title):
        """Serve the page with backlinks."""

        self.storage.reopen()
        self.index.update(self)
        page = self.get_page(request, title)
        html = page.template('backlinks.html',
                             pages=self.index.page_backlinks(title))
        response = WikiResponse(html, mimetype='text/html')
        response.set_etag('/+search/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    @URL('/+download/scripts.js')
    def scripts_js(self, request):
        """Server the default scripts"""

        return self._serve_default(request, 'scripts.js', self.scripts,
                                   'text/javascript')

    @URL('/+download/style.css')
    def style_css(self, request):
        """Serve the default style"""

        return self._serve_default(request, 'style.css', self.style,
                                   'text/css')

    @URL('/+download/pygments.css')
    def pygments_css(self, request):
        """Serve the default pygments style"""

        _ = self.gettext
        if pygments is None:
            raise error.NotImplementedErr(
                _(u"Code highlighting is not available."))

        pygments_style = self.pygments_style
        if pygments_style not in pygments.styles.STYLE_MAP:
            pygments_style = 'default'
        formatter = pygments.formatters.HtmlFormatter(style=pygments_style)
        style_defs = formatter.get_style_defs('.highlight')
        return self._serve_default(request, 'pygments.css', style_defs,
                                   'text/css')

    @URL('/favicon.ico')
    def favicon_ico(self, request):
        """Serve the default favicon."""

        return self._serve_default(request, 'favicon.ico', self.icon,
                                   'image/x-icon')

    @URL('/robots.txt')
    def robots_txt(self, request):
        """Serve the robots directives."""

        robots = ('User-agent: *\r\n'
                  'Disallow: /+*\r\n'
                  'Disallow: /%2B*\r\n'
                  'Disallow: /+edit\r\n'
                  'Disallow: /+feed\r\n'
                  'Disallow: /+history\r\n'
                  'Disallow: /+search\r\n'
                  'Disallow: /+hg\r\n')
        return self._serve_default(request, 'robots.txt', robots,
                                   'text/plain')

    @URL('/+hg<all:path>', methods=['GET', 'POST', 'HEAD'])
    def hgweb(self, request, path=None):
        """
        Serve the pages repository on the web like a normal hg repository.
        """

        _ = self.gettext
        if not self.config.get_bool('hgweb', False):
            raise error.ForbiddenErr(_(u'Repository access disabled.'))
        app = mercurial.hgweb.request.wsgiapplication(
            lambda: mercurial.hgweb.hgweb(self.storage.repo, self.site_name))

        def hg_app(env, start):
            env = request.environ
            prefix = '/+hg'
            if env['PATH_INFO'].startswith(prefix):
                env["PATH_INFO"] = env["PATH_INFO"][len(prefix):]
                env["SCRIPT_NAME"] += prefix
            return app(env, start)
        return hg_app

    @URL('/off-with-his-head', methods=['GET'])
    def die(self, request):
        """Terminate the standalone server if invoked from localhost."""

        _ = self.gettext
        if not request.remote_addr.startswith('127.'):
            raise error.ForbiddenErr(
                _(u'This URL can only be called locally.'))

        def agony():
            yield u'Oh dear!'
            self.dead = True
        return WikiResponse(agony(), mimetype='text/plain')

    @werkzeug.responder
    def application(self, environ, start):
        """The main application loop."""

        adapter = self.url_map.bind_to_environ(environ)
        request = WikiRequest(self, adapter, environ)
        try:
            try:
                endpoint, values = adapter.match()
                return endpoint(request, **values)
            except werkzeug.exceptions.HTTPException, err:
                return err
        finally:
            request.cleanup()
            del request
            del adapter
