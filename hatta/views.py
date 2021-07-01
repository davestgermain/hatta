# -*- coding: utf-8 -*-

import itertools
import re
import datetime
import hashlib
import os
import tempfile
import pkgutil

from werkzeug import urls, wsgi
from werkzeug.utils import html, escape, redirect
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
from hatta.response import response, WikiResponse


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
    resp = WikiResponse(
        content,
        mimetype=mime,
    )
    resp.set_etag('/%s/-1' % title)
    resp.make_conditional(request)
    resp.headers.add('Cache-Control', 'max-age=31536000')
    return resp



@URL('/<title:title>')
@URL('/')
def view(request, title=None):
    _ = request.wiki.gettext
    if title is None:
        title = request.wiki.front_page
    page = hatta.page.get_page(request, title)
    try:
        content = page.view_content()
    except hatta.error.NotFoundErr:
        if request.wiki.fallback_url:
            url = request.wiki.fallback_url
            if '%s' in url:
                url = url % urls.url_quote(title)
            else:
                url = "%s/%s" % (url, urls.url_quote(title))
            return redirect(url, code=303)
        if request.wiki.read_only:
            raise hatta.error.NotFoundErr(_("Page not found."))

        url = request.get_url(title, 'edit', external=True)
        return redirect(url, code=303)
    phtml = page.template("page.html", content=content)
    dependencies = page.dependencies()
    etag = '/(%s)' % ','.join(dependencies)
    return response(request, title, phtml, etag=etag, rev=page.revision.rev, date=page.revision.date)


@URL('/+history/<title:title>/<title:rev>')
def revision(request, title, rev):
    _ = request.wiki.gettext
    text = request.wiki.storage.get_revision(title, rev).text
    link = html.a(html(title),
                           href=request.get_url(title))
    content = [
        html.p(
            html(
                _('Content of revision %(rev)s of page %(title)s:'))
            % {'rev': rev[:8], 'title': link}),
        html.pre(html(text)),
    ]
    special_title = _('Revision of "%(title)s"') % {'title': title}
    page = hatta.page.get_page(request, title)
    resp = page.template('page_special.html', content=content,
                         special_title=special_title)
    return response(request, title, resp, rev=rev, etag='/old')


@URL('/+version/')
@URL('/+version/<title:title>')
def version(request, title=None):
    if title is None:
        version = request.wiki.storage.repo_revision
    else:
        try:
            version, x, x, x = next(request.wiki.storage.page_history(title))
        except StopIteration:
            version = 0
    return WikiResponse('%d' % version, mimetype="text/plain")


@URL('/+edit/<title:title>', methods=['POST'])
def save(request, title):
    _ = request.wiki.gettext
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
            lines = [html.p(html(
                _('No preview for binaries.')))]
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
        if 'href="' in comment or 'http:' in comment:
            raise hatta.error.ForbiddenErr()
        author = request.get_author()
        text = request.form.get("text")
        try:
            parent = request.form.get("parent")
        except (ValueError, TypeError):
            parent = None
        page = hatta.page.get_page(request, title)
        saved_titles = [title]
        if text is not None:
            if title == request.wiki.locked_page:
                for link, label in page.extract_links(text):
                    if title == link:
                        raise hatta.error.ForbiddenErr(
                            _("This page is locked."))
            if text.strip() == '':
                request.wiki.storage.delete_page(title, author, comment)
                url = request.get_url(request.wiki.front_page)
            else:
                with request.wiki.storage:
                    request.wiki.storage.save_text(title, text, author, comment,
                                       parent)
        elif page.mime == 'application/hatta+zip' and request.wiki.allow_bulk_uploads:
            # special case for uploading zip file of multiple pages
            upload = request.files.get('data')
            import zipfile, tempfile
            tfname = tempfile.mktemp()
            upload.save(tfname)
            try:
                with open(tfname, 'rb') as tf, zipfile.ZipFile(tf) as zf, request.wiki.storage:
                    for name in zf.namelist():
                        if name[0] in '._/~!+=-#%&':
                            continue
                        elif name not in request.wiki.storage:
                            # can't replace existing pages
                            hatta.page.check_lock(request.wiki, name)
                            with zf.open(name) as f:
                                data = f.read()
                                if data:
                                    request.wiki.storage.save_data(
                                        name,
                                        data,
                                        author,
                                        comment
                                    )
                            url = request.get_url(name)
                            saved_titles.append(name)
            finally:
                os.unlink(tfname)
        else:
            text = ''
            upload = request.files.get('data')
            with request.wiki.storage:
                if upload and upload.stream and upload.filename:
                    f = upload.stream
                    request.wiki.storage.save_data(title, f.read(), author,
                                           comment, parent)
                else:
                    request.wiki.storage.delete_page(title, author, comment)
                    url = request.get_url(request.wiki.front_page)
        request.wiki.index.reindex(request.wiki, saved_titles)
    response = redirect(url, code=303)
    response.set_cookie('author',
                        urls.url_quote(request.get_author()),
                        max_age=604800)
    return response

@URL('/+edit/<title:title>', methods=['GET'])
def edit(request, title, preview=None, captcha_error=None):
    hatta.page.check_lock(request.wiki, title)
    exists = title in request.wiki.storage
    page = hatta.page.get_page(request, title)
    phtml = page.render_editor(preview, captcha_error)
    if not exists:
        resp = WikiResponse(phtml, mimetype="text/html",
                                 status='404 Not found')

    elif preview:
        resp = WikiResponse(phtml, mimetype="text/html")
    else:
        resp = response(request, title, phtml, etag='/edit', rev=page.revision.rev, date=page.revision.date)
    resp.headers.add('Cache-Control', 'no-cache')
    return resp

@URL('/+feed/atom')
@URL('/+feed/rss')
def atom(request):
    _ = request.wiki.gettext
    history = itertools.islice(_changes_list(request), None, 10, None)
    unique_titles = set()
    entries = []
    last_date = None
    for date, url, title, author, comment in history:
        if title in unique_titles:
            continue
        if last_date is None:
            last_date = date
        unique_titles.add(title)
        if url.count('/') <= 2:
            url = request.get_url(title)
        entries.append({
            'title': title,
            'comment': comment,
            'author': author,
            'url': url,
            'updated': date,
        })

    if not last_date:
        last_date = datetime.datetime.utcnow()

    page = hatta.page.get_page(request, '')

    phtml = page.template('atom.xml',
         url=request.adapter.build('view', force_external=True),
         wiki=request.wiki,
         last_date=last_date,
         feed_url=urls.url_unquote(request.url),
         subtitle=_('Track the most recent changes to the wiki in this feed.'),
         entries=entries,
    )
    resp = response(
        request,
        'atom',
        phtml,
        '/+feed',
        'application/xml',
        rev=request.wiki.storage.repo_revision,
        date=last_date,
    )
    return resp


@URL('/+download/<title:title>:<title:rev>')
def download_rev(request, title, rev):
    """Serve the raw content of a page directly from disk."""

    mime = hatta.page.page_mime(title)
    if mime == 'text/x-wiki':
        mime = 'text/plain'
    revision = request.wiki.storage.get_revision(title, rev)
    data = wsgi.wrap_file(request.environ, revision.file)
    resp = response(request,
        title,
        data,
         '/download',
        mime,
        rev=revision.rev,
        date=revision.date
    )
    # give browsers a useful filename hint
    if rev:
        filename = '%s-%s' % (rev, title)
    else:
        filename = title
    resp.headers.add('Content-Disposition', 'filename="%s"' % urls.url_quote(filename))
    resp.direct_passthrough = True
    return resp


@URL('/+download/<title:title>')
def download(request, title):
    """Serve the raw content of a page directly from disk."""
    return download_rev(request, title, None)


@URL('/+render/<title:title>')
def render(request, title):
    """Serve a thumbnail or otherwise rendered content."""

    page = hatta.page.get_page(request, title)
    try:
        if request.wiki.cache is None:
            raise NotImplementedError()
        cache_filename, cache_mime = page.render_mime()
        render = page.render_cache
    except (AttributeError, NotImplementedError):
        return download(request, title)

    cache_key = hashlib.md5(
        '{}{}{}'.format(title, page.revision.rev, page.render_size).encode('utf8')
    ).hexdigest()
    data = request.wiki.cache.get(cache_key)
    if data is None:
        try:
            data = render()
        except hatta.error.UnsupportedMediaTypeErr:
            return download(request, title)
        request.wiki.cache.set(cache_key, data, timeout=86400)

    resp = response(request, title, data, '/render', cache_mime, rev=page.revision.rev, date=page.revision.date)
    return resp


@URL('/+undo/<title:title>', methods=['POST'])
def undo(request, title):
    """Revert a change to a page."""

    _ = request.wiki.gettext
    hatta.page.check_lock(request.wiki, title)
    author = request.get_author()
    rev = None
    for key in request.form:
        if key != 'parent':
            rev = key
            break
    if rev is not None:
        try:
            parent = request.form.get("parent")
        except (ValueError, TypeError):
            parent = None
        with request.wiki.storage:
            request.wiki.index.update(request.wiki)
            if rev == parent:
                comment = _('Delete page %(title)s') % {'title': title}
                data = ''
                request.wiki.storage.delete_page(title, author, comment)
            else:
                comment = _('Undo of change %(rev)s of page %(title)s') % {
                    'rev': rev, 'title': title}
                data = request.wiki.storage.get_previous_revision(title, rev).data
                request.wiki.storage.save_data(title, data, author, comment)
        page = hatta.page.get_page(request, title)
        request.wiki.index.update_page(page, title, data=data)
    url = request.adapter.build('history', {'title': title},
                                method='GET', force_external=True)
    return redirect(url, 303)

@URL('/+history/<title:title>')
def history(request, title):
    """Display history of changes of a page."""

    max_rev = '0' * 40
    history = []
    title = urls.url_unquote(title)
    page = hatta.page.get_page(request, title)
    # only text pages should show a link for diffs
    can_diff = getattr(page, 'diff_content', False)

    if title not in request.wiki.storage:
        _ = request.wiki.gettext
        raise hatta.error.NotFoundErr(_("Page not found."))

    for item in request.wiki.storage.page_history(title):
        parent = item['parent']
        if can_diff:
            if parent:
                date_url = request.adapter.build('diff', {
                    'title': title,
                    'from_rev': parent,
                    'to_rev': item['rev'],
                })
            else:
                date_url = request.adapter.build('revision', {
                    'title': title,
                    'rev': item['rev'],
                })
        else:
            date_url = request.adapter.build('download_rev', {
                    'title': title,
                    'rev': item['rev']
                })
        item['date_url'] = date_url
        history.append(item)
        if item['rev']:
            max_rev = item['rev']

    phtml = page.template('history.html',
                         history=history,
                         date_html=hatta.page.date_html,
                         parent_rev=max_rev)
    resp = response(request, title, phtml, '/history')
    return resp


def _changes_list(request):
    last = {}
    lastrev = {}
    count = 0
    for item in request.wiki.storage.history():
        title = item['title']
        rev = item['rev']
        parent = item['parent']
        date = item['date']
        author = item['author']
        comment = item['comment']

        if (author, comment) == last.get(title, (None, None)):
            continue
        count += 1
        if count > 100:
            break
        if parent:
            date_url = request.adapter.build('diff', {
                'title': title,
                'from_rev': parent,
                'to_rev': lastrev.get(title, rev),
            })
        elif rev == 0:
            date_url = request.adapter.build('revision', {
                'title': title,
                'rev': rev,
            })
        else:
            date_url = request.adapter.build('history', {'title': urls.url_quote(title, safe='')})
        last[title] = author, comment
        lastrev[title] = rev

        yield date, date_url, title, author, comment


@URL('/+history/')
def recent_changes(request):
    """Serve the recent changes page."""

    rev = request.wiki.storage.repo_revision
    if request.wiki.cache:
        cache_key = '+history:%s' % rev
        changes = request.wiki.cache.get(cache_key)
        if changes is None:
            changes = list(_changes_list(request))
            request.wiki.cache.set(cache_key, changes, 0)
    else:
        changes = _changes_list(request)
    page = hatta.page.get_page(request, '')
    phtml = page.template('changes.html', changes=changes,
                         date_html=hatta.page.date_html)
    resp = WikiResponse(phtml, mimetype='text/html')
    resp.set_etag('/history/%s' % rev)
    resp.make_conditional(request)
    return resp

@URL('/+history/<title:title>/<title:from_rev>:<title:to_rev>')
def diff(request, title, from_rev, to_rev):
    """Show the differences between specified revisions."""

    _ = request.wiki.gettext
    page = hatta.page.get_page(request, title)
    build = request.adapter.build
    from_url = build('revision', {'title': title, 'rev': from_rev})
    to_url = build('revision', {'title': title, 'rev': to_rev})
    a = html.a
    links = {
        'link1': a(str(from_rev)[:8], href=from_url),
        'link2': a(str(to_rev)[:8], href=to_url),
        'link': a(html(title), href=request.get_url(title)),
    }
    message = html(_(
        'Differences between revisions %(link1)s and %(link2)s '
        'of page %(link)s.')) % links
    diff_content = getattr(page, 'diff_content', None)
    if diff_content:
        from_text = request.wiki.storage.get_revision(page.title, from_rev).text
        to_text = request.wiki.storage.get_revision(page.title, to_rev).text
        content = page.diff_content(from_text, to_text, message)
    else:
        content = [html.p(html(
            _("Diff not available for this kind of pages.")))]
    special_title = _('Diff for "%(title)s"') % {'title': title}
    phtml = page.template('page_special.html', content=content,
                        special_title=special_title)
    resp = WikiResponse(phtml, mimetype='text/html')
    return resp


@URL('/+index')
def all_pages(request):
    """Show index of all pages in the request.wiki."""

    _ = request.wiki.gettext
    page = hatta.page.get_page(request, '')
    phtml = page.template('list.html',
                         pages=sorted(request.wiki.storage.all_pages()),
                         class_='index',
                         message=_('Index of all pages'),
                         special_title=_('Page Index'))
    resp = WikiResponse(phtml, mimetype='text/html')
    resp.set_etag('/+index/%s' % request.wiki.storage.repo_revision)
    resp.make_conditional(request)
    return resp


@URL('/+sister-index')
def sister_pages(request):
    """Show index of all pages in a format suitable for SisterPages."""

    text = [
        '%s%s %s\n' % (request.base_url, request.get_url(title), title)
        for title in request.wiki.storage.all_pages()
    ]
    text.sort()
    resp = WikiResponse(text, mimetype='text/plain')
    resp.set_etag('/+sister-index/%s' % request.wiki.storage.repo_revision)
    resp.make_conditional(request)
    return resp


@URL('/+orphaned')
def orphaned(request):
    """Show all pages that don't have backlinks."""

    _ = request.wiki.gettext
    page = hatta.page.get_page(request, '')
    orphaned = request.wiki.index.orphaned_pages(request.wiki)
    phtml = page.template('list.html',
                         pages=orphaned,
                         class_='orphaned',
                         message=_('List of pages with no links to them'),
                         special_title=_('Orphaned pages'))
    resp = WikiResponse(phtml, mimetype='text/html')
    resp.set_etag('/+orphaned/%s' % request.wiki.storage.repo_revision)
    resp.make_conditional(request)
    return resp

@URL('/+wanted')
def wanted(request):
    """Show all pages that don't exist yet, but are linked."""

    def _wanted_pages_list():
        for refs, title in request.wiki.index.wanted_pages(request.wiki):
            if not (hatta.parser.external_link(title) or title.startswith('+')
                    or title.startswith(':')):
                yield refs, title

    page = hatta.page.get_page(request, '')
    phtml = page.template('wanted.html', pages=_wanted_pages_list())
    resp = WikiResponse(phtml, mimetype='text/html')
    resp.set_etag('/+wanted/%s' % request.wiki.storage.repo_revision)
    resp.make_conditional(request)
    return resp

@URL('/+search', methods=['GET', 'POST'])
def search(request):
    """Serve the search results page."""

    _ = request.wiki.gettext

    def highlight_html(m):
        return html.b(m.group(0), class_="highlight")

    def search_snippet(title, words):
        """Extract a snippet of text for search results."""

        try:
            text = request.wiki.storage.get_revision(title).text
        except hatta.error.NotFoundErr:
            return ''
        regexp = re.compile("|".join(re.escape(w) for w in words),
                            re.U | re.I)
        match = regexp.search(text)
        if match is None:
            return ""
        position = match.start()
        min_pos = max(position - 60, 0)
        max_pos = min(position + 60, len(text))
        snippet = escape(text[min_pos:max_pos])
        phtml = regexp.sub(highlight_html, snippet)
        return phtml

    def page_search(words, page, request):
        """Display the search results."""

        h = html
        request.wiki.index.update(request.wiki)
        result = sorted(request.wiki.index.find(words), key=lambda x: -x[0])
        yield html.p(h(_('%d page(s) containing all words:')
                              % len(result)))
        yield '<ol id="hatta-search-results">'
        for number, (score, title) in enumerate(result):
            yield h.li(h.b(page.wiki_link(title)), ' ', h.i(str(score)),
                       h.div(search_snippet(title, words),
                             class_="hatta-snippet"),
                       id_="search-%d" % (number + 1))
        yield '</ol>'

    query = request.values.get('q', '').strip()
    page = hatta.page.get_page(request, '')
    if not query:
        url = request.get_url(view='all_pages', external=True)
        return redirect(url, code=303)
    words = tuple(request.wiki.index.split_text(query))
    if not words:
        words = (query,)
    title = _('Searching for "%s"') % " ".join(words)
    content = page_search(words, page, request)
    phtml = page.template('page_special.html', content=content,
                         special_title=title)
    return WikiResponse(phtml, mimetype='text/html')

@URL('/+search/<title:title>', methods=['GET', 'POST'])
def backlinks(request, title):
    """Serve the page with backlinks."""

    request.wiki.index.update(request.wiki)
    page = hatta.page.get_page(request, title)
    phtml = page.template('backlinks.html',
                         pages=request.wiki.index.page_backlinks(title))
    resp = WikiResponse(phtml, mimetype='text/html')
    resp.set_etag('/+search/%s' % request.wiki.storage.repo_revision)
    resp.make_conditional(request)
    return resp

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
            _("Code highlighting is not available."))

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
        raise hatta.error.ForbiddenErr(_('Repository access disabled.'))

    import mercurial
    app = mercurial.hgweb.request.wsgiapplication(
        lambda: mercurial.hgweb.hgweb(request.wiki.storage.repo, request.wiki.site_name.encode('utf8')))

    def hg_app(env, start):
        env = request.environ
        prefix = '/+hg'
        if env['PATH_INFO'].startswith(prefix):
            env["PATH_INFO"] = env["PATH_INFO"][len(prefix):]
            env["SCRIPT_NAME"] += prefix
        return app(env, start)
    return hg_app

