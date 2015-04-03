# -*- coding: utf-8 -*-

import itertools
import re
import datetime
import os
import tempfile
import pkgutil

import werkzeug
captcha = None
try:
    from recaptcha.client import captcha
except ImportError:
    pass
pygments = None
try:
    import pygments
except ImportError:
    pass

import hatta.page
import hatta.parser
import hatta.error
import hatta.response

import mercurial


class URL(object):
    """A decorator for marking methods as endpoints for URLs."""

    urls = []

    def __init__(self, url, methods=None):
        """Create a decorator with specified parameters."""

        self.url = url
        self.methods = methods or ['GET', 'HEAD']

    def __call__(self, func):
        """The actual decorator only records the data."""

        self.urls.append((func.__name__, func, self.url, self.methods))
        return func

    @classmethod
    def get_rules(cls):
        """Returns the routing rules."""

        return [
            werkzeug.routing.Rule(url, endpoint=name, methods=methods)
            for name, func, url, methods in cls.urls
        ]

    @classmethod
    def get_views(cls):
        """Returns a dict of views."""

        return dict((name, func) for name, func, url, methods in cls.urls)


def _serve_default(request, title, content=None, mime=None):
    """Some pages have their default content."""

    if title in request.wiki.storage:
        return download(request, title)
    if content is None:
        content = pkgutil.get_data('hatta', os.path.join('static', title))
    mime = mime or 'application/octet-stream'
    response = hatta.response.WikiResponse(
        content,
        mimetype=mime,
    )
    response.set_etag('/%s/-1' % title)
    response.make_conditional(request)
    return response



@URL('/<title:title>')
@URL('/')
def view(request, title=None):
    _ = request.wiki.gettext
    request.wiki.refresh()
    if title is None:
        title = request.wiki.front_page
    page = hatta.page.get_page(request, title)
    try:
        content = page.view_content()
    except hatta.error.NotFoundErr:
        if request.wiki.fallback_url:
            url = request.wiki.fallback_url
            if '%s' in url:
                url = url % werkzeug.url_quote(title)
            else:
                url = "%s/%s" % (url, werkzeug.url_quote(title))
            return werkzeug.routing.redirect(url, code=303)
        if request.wiki.read_only:
            raise hatta.error.NotFoundErr(_(u"Page not found."))

        url = request.get_url(title, 'edit', external=True)
        return werkzeug.routing.redirect(url, code=303)
    html = page.template("page.html", content=content)
    dependencies = page.dependencies()
    etag = '/(%s)' % u','.join(dependencies)
    return hatta.response.response(request, title, html, etag=etag)

@URL('/+history/<title:title>/<int:rev>')
def revision(request, title, rev):
    _ = request.wiki.gettext
    request.wiki.refresh()
    text = request.wiki.storage.revision_text(title, rev)
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
    page = hatta.page.get_page(request, title)
    html = page.template('page_special.html', content=content,
                         special_title=special_title)
    response = hatta.response.response(request, title, html, rev=rev, etag='/old')
    return response

@URL('/+version/')
@URL('/+version/<title:title>')
def version(request, title=None):
    if title is None:
        version = request.wiki.storage.repo_revision()
    else:
        try:
            version, x, x, x = request.wiki.storage.page_history(title).next()
        except StopIteration:
            version = 0
    return hatta.response.WikiResponse('%d' % version, mimetype="text/plain")

@URL('/+edit/<title:title>', methods=['POST'])
def save(request, title):
    _ = request.wiki.gettext
    request.wiki.refresh()
    hatta.page.check_lock(request.wiki, title)
    url = request.get_url(title)
    if request.form.get('cancel'):
        if title not in request.wiki.storage:
            url = request.get_url(request.wiki.front_page)
    if request.form.get('preview'):
        text = request.form.get("text")
        if text is not None:
            lines = text.split('\n')
        else:
            lines = [werkzeug.html.p(werkzeug.html(
                _(u'No preview for binaries.')))]
        return edit(request, title, preview=lines)
    elif request.form.get('save'):
        if captcha and request.wiki.recaptcha_private_key:
            response = captcha.submit(
                request.form.get('recaptcha_challenge_field', ''),
                request.form.get('recaptcha_response_field', ''),
                request.wiki.recaptcha_private_key, request.remote_addr)
            if not response.is_valid:
                text = request.form.get("text", '')
                return edit(request, title, preview=text.split('\n'),
                                 captcha_error=response.error_code)
        comment = request.form.get("comment", "")
        if u'href="' in comment or u'http:' in comment:
            raise hatta.error.ForbiddenErr()
        author = request.get_author()
        text = request.form.get("text")
        try:
            parent = int(request.form.get("parent"))
        except (ValueError, TypeError):
            parent = None
        page = hatta.page.get_page(request, title)
        if text is not None:
            if title == request.wiki.locked_page:
                for link, label in page.extract_links(text):
                    if title == link:
                        raise hatta.error.ForbiddenErr(
                            _(u"This page is locked."))
            if text.strip() == '':
                request.wiki.storage.delete_page(title, author, comment)
                url = request.get_url(request.wiki.front_page)
            else:
                request.wiki.storage.save_text(title, text, author, comment,
                                       parent)
        else:
            text = u''
            upload = request.files.get('data')
            if upload and upload.stream and upload.filename:
                f = upload.stream
                request.wiki.storage.save_data(title, f.read(), author,
                                       comment, parent)
            else:
                request.wiki.storage.delete_page(title, author, comment)
                url = request.get_url(request.wiki.front_page)
        request.wiki.index.update(request.wiki)
    response = werkzeug.routing.redirect(url, code=303)
    response.set_cookie('author',
                        werkzeug.url_quote(request.get_author()),
                        max_age=604800)
    return response

@URL('/+edit/<title:title>', methods=['GET'])
def edit(request, title, preview=None, captcha_error=None):
    hatta.page.check_lock(request.wiki, title)
    request.wiki.refresh()
    exists = title in request.wiki.storage
    if exists:
        request.wiki.storage.reopen()
    page = hatta.page.get_page(request, title)
    html = page.render_editor(preview, captcha_error)
    if not exists:
        response = hatta.response.WikiResponse(html, mimetype="text/html",
                                 status='404 Not found')

    elif preview:
        response = hatta.response.WikiResponse(html, mimetype="text/html")
    else:
        response = hatta.response.response(request, title, html, '/edit')
    response.headers.add('Cache-Control', 'no-cache')
    return response

@URL('/+feed/atom')
@URL('/+feed/rss')
def atom(request):
    _ = request.wiki.gettext
    feed = werkzeug.contrib.atom.AtomFeed(request.wiki.site_name,
        feed_url=request.url,
        url=request.adapter.build('view', force_external=True),
        subtitle=_(u'Track the most recent changes to the wiki '
                   u'in this feed.'))
    history = itertools.islice(request.wiki.storage.history(), None, 10, None)
    unique_titles = set()
    for title, rev, date, author, comment in history:
        if title in unique_titles:
            continue
        unique_titles.add(title)
        if rev > 0:
            url = request.adapter.build('diff', {
                'title': title,
                'from_rev': rev - 1,
                'to_rev': rev,
            }, force_external=True)
        else:
            url = request.adapter.build('view', {
                'title': title,
            }, force_external=True)
        feed.add(title, comment, content_type="text", author=author,
                 url=url, updated=date)
    rev = request.wiki.storage.repo_revision()
    response = hatta.response.response(request, 'atom', feed.generate(),
                                       '/+feed', 'application/xml', rev)
    response.make_conditional(request)
    return response

@URL('/+download/<title:title>')
def download(request, title):
    """Serve the raw content of a page directly from disk."""

    request.wiki.refresh()
    mime = hatta.page.page_mime(title)
    if mime == 'text/x-wiki':
        mime = 'text/plain'
    data = request.wiki.storage.page_data(title)
    response = hatta.response.response(request, title, data,
                             '/download', mime, size=len(data))
    response.direct_passthrough = True
    return response

@URL('/+render/<title:title>')
def render(request, title):
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

    request.wiki.refresh()
    page = hatta.page.get_page(request, title)
    try:
        cache_filename, cache_mime = page.render_mime()
        render = page.render_cache
    except (AttributeError, NotImplementedError):
        return download(request, title)

    cache_dir = os.path.join(request.wiki.cache, 'render',
                              werkzeug.url_quote(title, safe=''))
    cache_file = os.path.join(cache_dir, cache_filename)
    rev, date, author, comment = request.wiki.storage.page_meta(title)
    cache_mtime, cache_size = file_time_and_size(cache_file)
    if date > datetime.datetime.fromtimestamp(cache_mtime):
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        try:
            temp_dir = tempfile.mkdtemp(dir=cache_dir)
            result_file = render(temp_dir)
            mercurial.util.rename(result_file, cache_file)
        except hatta.error.UnsupportedMediaTypeErr:
            return download(request, title)
        finally:
            rm_temp_dir(temp_dir)
    try:
        wrap_file = werkzeug.wrap_file
    except AttributeError:
        wrap_file = lambda x, y: y
    f = wrap_file(request.environ, open(cache_file))
    response = hatta.response.response(request, title, f, '/render', cache_mime,
                             size=cache_size)
    response.direct_passthrough = True
    return response

@URL('/+undo/<title:title>', methods=['POST'])
def undo(request, title):
    """Revert a change to a page."""

    _ = request.wiki.gettext
    request.wiki.refresh()
    hatta.page.check_lock(request.wiki, title)
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
        request.wiki.storage.reopen()
        request.wiki.index.update(request.wiki)
        if rev == 0:
            comment = _(u'Delete page %(title)s') % {'title': title}
            data = ''
            request.wiki.storage.delete_page(title, author, comment)
        else:
            comment = _(u'Undo of change %(rev)d of page %(title)s') % {
                'rev': rev, 'title': title}
            data = request.wiki.storage.page_revision(title, rev - 1)
            request.wiki.storage.save_data(title, data, author, comment, parent)
        page = hatta.page.get_page(request, title)
        request.wiki.index.update_page(page, title, data=data)
    url = request.adapter.build('history', {'title': title},
                                method='GET', force_external=True)
    return werkzeug.redirect(url, 303)

@URL('/+history/<title:title>')
def history(request, title):
    """Display history of changes of a page."""

    max_rev = -1
    history = []
    request.wiki.refresh()
    page = hatta.page.get_page(request, title)
    for rev, date, author, comment in request.wiki.storage.page_history(title):
        if max_rev < rev:
            max_rev = rev
        if rev > 0:
            date_url = request.adapter.build('diff', {
                'title': title,
                'from_rev': rev - 1,
                'to_rev': rev,
            })
        else:
            date_url = request.adapter.build('revision', {
                'title': title,
                'rev': rev,
            })
        history.append((date, date_url, rev, author, comment))
    html = page.template('history.html', history=history,
                         date_html=hatta.page.date_html, parent=max_rev)
    response = hatta.response.response(request, title, html, '/history')
    return response

@URL('/+history/')
def recent_changes(request):
    """Serve the recent changes page."""

    def _changes_list():
        last = {}
        lastrev = {}
        count = 0
        for title, rev, date, author, comment in request.wiki.storage.history():
            if (author, comment) == last.get(title, (None, None)):
                continue
            count += 1
            if count > 100:
                break
            if rev > 0:
                date_url = request.adapter.build('diff', {
                    'title': title,
                    'from_rev': rev - 1,
                    'to_rev': lastrev.get(title, rev),
                })
            elif rev == 0:
                date_url = request.adapter.build('revision', {
                    'title': title,
                    'rev': rev,
                })
            else:
                date_url = request.adapter.build('history', {'title': title})
            last[title] = author, comment
            lastrev[title] = rev

            yield date, date_url, title, author, comment

    request.wiki.refresh()
    page = hatta.page.get_page(request, '')
    html = page.template('changes.html', changes=_changes_list(),
                         date_html=hatta.page.date_html)
    response = hatta.response.WikiResponse(html, mimetype='text/html')
    response.set_etag('/history/%d' % request.wiki.storage.repo_revision())
    response.make_conditional(request)
    return response

@URL('/+history/<title:title>/<int:from_rev>:<int:to_rev>')
def diff(request, title, from_rev, to_rev):
    """Show the differences between specified revisions."""

    _ = request.wiki.gettext
    request.wiki.refresh()
    page = hatta.page.get_page(request, title)
    build = request.adapter.build
    from_url = build('revision', {'title': title, 'rev': from_rev})
    to_url = build('revision', {'title': title, 'rev': to_rev})
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
        from_text = request.wiki.storage.revision_text(page.title, from_rev)
        to_text = request.wiki.storage.revision_text(page.title, to_rev)
        content = page.diff_content(from_text, to_text, message)
    else:
        content = [werkzeug.html.p(werkzeug.html(
            _(u"Diff not available for this kind of pages.")))]
    special_title = _(u'Diff for "%(title)s"') % {'title': title}
    html = page.template('page_special.html', content=content,
                        special_title=special_title)
    response = hatta.response.WikiResponse(html, mimetype='text/html')
    return response

@URL('/+index')
def all_pages(request):
    """Show index of all pages in the request.wiki."""

    _ = request.wiki.gettext
    request.wiki.refresh()
    page = hatta.page.get_page(request, '')
    html = page.template('list.html',
                         pages=sorted(request.wiki.storage.all_pages()),
                         class_='index',
                         message=_(u'Index of all pages'),
                         special_title=_(u'Page Index'))
    response = hatta.response.WikiResponse(html, mimetype='text/html')
    response.set_etag('/+index/%d' % request.wiki.storage.repo_revision())
    response.make_conditional(request)
    return response

@URL('/+sister-index')
def sister_pages(request):
    """Show index of all pages in a format suitable for SisterPages."""

    text = [
        '%s%s %s\n' % (request.base_url, request.get_url(title), title)
        for title in request.wiki.storage.all_pages()
    ]
    text.sort()
    response = hatta.response.WikiResponse(text, mimetype='text/plain')
    response.set_etag('/+sister-index/%d' % request.wiki.storage.repo_revision())
    response.make_conditional(request)
    return response

@URL('/+orphaned')
def orphaned(request):
    """Show all pages that don't have backlinks."""

    _ = request.wiki.gettext
    request.wiki.refresh()
    page = hatta.page.get_page(request, '')
    orphaned = [
        title
        for title in request.wiki.index.orphaned_pages()
        if title in request.wiki.storage
    ]
    html = page.template('list.html',
                         pages=orphaned,
                         class_='orphaned',
                         message=_(u'List of pages with no links to them'),
                         special_title=_(u'Orphaned pages'))
    response = hatta.response.WikiResponse(html, mimetype='text/html')
    response.set_etag('/+orphaned/%d' % request.wiki.storage.repo_revision())
    response.make_conditional(request)
    return response

@URL('/+wanted')
def wanted(request):
    """Show all pages that don't exist yet, but are linked."""

    def _wanted_pages_list():
        for refs, title in request.wiki.index.wanted_pages():
            if not (hatta.parser.external_link(title) or title.startswith('+')
                    or title.startswith(':')):
                yield refs, title

    request.wiki.refresh()
    page = hatta.page.get_page(request, '')
    html = page.template('wanted.html', pages=_wanted_pages_list())
    response = hatta.response.WikiResponse(html, mimetype='text/html')
    response.set_etag('/+wanted/%d' % request.wiki.storage.repo_revision())
    response.make_conditional(request)
    return response

@URL('/+search', methods=['GET', 'POST'])
def search(request):
    """Serve the search results page."""

    _ = request.wiki.gettext

    def highlight_html(m):
        return werkzeug.html.b(m.group(0), class_="highlight")

    def search_snippet(title, words):
        """Extract a snippet of text for search results."""

        try:
            text = request.wiki.storage.page_text(title)
        except hatta.error.NotFoundErr:
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
        html = regexp.sub(highlight_html, snippet)
        return html

    def page_search(words, page, request):
        """Display the search results."""

        h = werkzeug.html
        request.wiki.index.update(request.wiki)
        result = sorted(request.wiki.index.find(words), key=lambda x: -x[0])
        yield werkzeug.html.p(h(_(u'%d page(s) containing all words:')
                              % len(result)))
        yield u'<ol id="hatta-search-results">'
        for number, (score, title) in enumerate(result):
            yield h.li(h.b(page.wiki_link(title)), u' ', h.i(str(score)),
                       h.div(search_snippet(title, words),
                             class_="hatta-snippet"),
                       id_="search-%d" % (number + 1))
        yield u'</ol>'

    query = request.values.get('q', u'').strip()
    request.wiki.refresh()
    page = hatta.page.get_page(request, '')
    if not query:
        url = request.get_url(view='all_pages', external=True)
        return werkzeug.routing.redirect(url, code=303)
    words = tuple(request.wiki.index.split_text(query))
    if not words:
        words = (query,)
    title = _(u'Searching for "%s"') % u" ".join(words)
    content = page_search(words, page, request)
    html = page.template('page_special.html', content=content,
                         special_title=title)
    return hatta.response.WikiResponse(html, mimetype='text/html')

@URL('/+search/<title:title>', methods=['GET', 'POST'])
def backlinks(request, title):
    """Serve the page with backlinks."""

    request.wiki.refresh()
    request.wiki.index.update(request.wiki)
    page = hatta.page.get_page(request, title)
    html = page.template('backlinks.html',
                         pages=request.wiki.index.page_backlinks(title))
    response = hatta.response.WikiResponse(html, mimetype='text/html')
    response.set_etag('/+search/%d' % request.wiki.storage.repo_revision())
    response.make_conditional(request)
    return response

@URL('/+download/scripts.js')
def scripts_js(request):
    """Server the default scripts"""

    return _serve_default(request, 'scripts.js',
                               mime='text/javascript')

@URL('/+download/style.css')
def style_css(request):
    """Serve the default style"""

    return _serve_default(request, 'style.css',
                               mime='text/css')

@URL('/+download/pygments.css')
def pygments_css(request):
    """Serve the default pygments style"""

    _ = request.wiki.gettext
    if pygments is None:
        raise hatta.error.NotImplementedErr(
            _(u"Code highlighting is not available."))

    pygments_style = request.wiki.pygments_style
    if pygments_style not in pygments.styles.STYLE_MAP:
        pygments_style = 'default'
    formatter = pygments.formatters.HtmlFormatter(style=pygments_style)
    style_defs = formatter.get_style_defs('.highlight')
    return _serve_default(request, 'pygments.css', style_defs,
                               'text/css')

@URL('/favicon.ico')
def favicon_ico(request):
    """Serve the default favicon."""

    return _serve_default(request, 'favicon.ico',
                               mime='image/x-icon')

@URL('/robots.txt')
def robots_txt(request):
    """Serve the robots directives."""

    return _serve_default(request, 'robots.txt',
                               mime='text/plain')

@URL('/+hg<all:path>', methods=['GET', 'POST', 'HEAD'])
def hgweb(request, path=None):
    """
    Serve the pages repository on the web like a normal hg repository.
    """

    _ = request.wiki.gettext
    if not request.wiki.config.get_bool('hgweb', False):
        raise hatta.error.ForbiddenErr(_(u'Repository access disabled.'))
    app = mercurial.hgweb.request.wsgiapplication(
        lambda: mercurial.hgweb.hgweb(request.wiki.storage.repo, request.wiki.site_name))

    def hg_app(env, start):
        env = request.environ
        prefix = '/+hg'
        if env['PATH_INFO'].startswith(prefix):
            env["PATH_INFO"] = env["PATH_INFO"][len(prefix):]
            env["SCRIPT_NAME"] += prefix
        return app(env, start)
    return hg_app

@URL('/off-with-his-head', methods=['GET'])
def die(request):
    """Terminate the standalone server if invoked from localhost."""

    _ = request.wiki.gettext
    if not request.remote_addr.startswith('127.'):
        raise hatta.error.ForbiddenErr(
            _(u'This URL can only be called locally.'))

    def agony():
        yield u'Oh dear!'
        request.wiki.dead = True
    return hatta.response.WikiResponse(agony(), mimetype='text/plain')
