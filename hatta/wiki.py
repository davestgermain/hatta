#!/usr/bin/python
# -*- coding: utf-8 -*-

import base64
import gettext
import os
import sys
import mimetypes
import re

import werkzeug
import werkzeug.routing

import pygments

from hatta import storage
from hatta import search
from hatta import page
from hatta import parser
from hatta import error


mimetypes.add_type('application/x-python', '.wsgi')
mimetypes.add_type('application/x-javascript', '.js')
mimetypes.add_type('text/x-rst', '.rst')


def page_mime(title):
    """
    Guess page's mime type ased on corresponding file name.
    Default ot text/x-wiki for files without an extension.

    >>> page_mime(u'something.txt')
    'text/plain'
    >>> page_mime(u'SomePage')
    'text/x-wiki'
    >>> page_mime(u'ąęśUnicodePage')
    'text/x-wiki'
    >>> page_mime(u'image.png')
    'image/png'
    >>> page_mime(u'style.css')
    'text/css'
    >>> page_mime(u'archive.tar.gz')
    'archive/gzip'
    """

    addr = title.encode('utf-8') # the encoding doesn't relly matter here
    mime, encoding = mimetypes.guess_type(addr, strict=False)
    if encoding:
        mime = 'archive/%s' % encoding
    if mime is None:
        mime = 'text/x-wiki'
    return mime


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
        # Whether to print the css for highlighting
        self.print_highlight_styles = True

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
        author = (self.form.get("author") or cookie or auth or self.remote_addr)
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

    regex='([^+%]|%[^2]|%2[^Bb]).*'


class WikiAllConverter(werkzeug.routing.BaseConverter):
    """Matches everything."""

    regex='.*'


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
    icon = base64.b64decode(
'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhki'
'AAAAAlwSFlzAAAEnQAABJ0BfDRroQAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBo'
'AAALWSURBVDiNbdNLaFxlFMDx//fd19x5JdNJm0lIImPaYm2MfSUggrssXBVaChUfi1JwpQtxK7gqu'
'LMbQQQ3bipU0G3Rgg98DBpraWob00kzM6Z5TF7tdObm3vvd46K0TBo/OLtzfnychxIRut+Zo2/19vT'
'kLxXze6biONbGJMRipL39MJyt33rvp+rVT7rzVTfw2vFzLxwcLf/V7oSq1W4hACIkIigUtnaoNecXG'
'2u14T8blQRAd2v7yyN/RLFR6IRM1iedSeFnUvhpDydlI9ow0lcedG3348c1djeQz+WcThjgYZMgGBG'
'SJMEYgzGGODLEoTBYGH4DeHcXoDSSzaRVogQjyaMwhtgYcoUco+Nl5qbnubFw7fr//uB2tXp78uj4c'
'0YJsSTESUxsDCemjjH6YhnbtbA8xaVv7n/0uGZHDx48aH8+17iLJQrf9vCdFL7tkcn7/Pb7r8zdmWP'
'2zqwopa7sAl4/cV4NlvrPbgch7aBN1vUIOw9ZWmmw2dqkb18fQSegOrOgfD9zahfQ37/3su+ljj1T6'
'uCnAyxtoZVGa41tWSilULWfCZdaPD986MsjQxOHdwC9PdmT2tLk0oozpxfYf2SZwp4Iz1X4UZWBe1+'
'z9+5X+OkiruWpYr744ZMmvjn5dvrwoVHLdRzWtobY2Kwx9soyz5ZXuV9fQ5pXCBabXKuXcBwbYwxYe'
'kIppTXAF5VP2xutrVYmm8bzM1z9foSZik1z1SWMNLW1AtMrB/gnnMJxbSxbUV2a/QHQT8Y4c+vvC8V'
'C74VCoZcodvnxux5Msg+THCSKHy2R48YgIb/crITrreZlEYl33MKrYycvvnx88p2BUkkpRyGSEBmDi'
'WI6QcC95UUqM9PBzdqN99fbzc9EJNwBKKUoFw+8NDY8/sFQ/8CE57l5pZRdX6kHqxurW43mv98urM9'
'fjJPouohE8NQ1dkEayAJ5wAe2gRawJSKmO/c/aERMn5m9/ksAAAAASUVORK5CYII=')
    scripts = r"""function hatta_dates(){var a=document.getElementsByTagName(
'abbr');var p=function(i){return('00'+i).slice(-2)};for(var i=0;i<a.length;++i)
{var n=a[i];if(n.className==='date'){var m=
/^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z$/.exec(
n.getAttribute('title'));var d=new Date(Date.UTC(+m[1],+m[2]-1,+m[3],+m[4],
+m[5],+m[6]));if(d){var b=-d.getTimezoneOffset()/60;if(b>=0){b="+"+b}
n.textContent=""+d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+
p(d.getHours())+":"+p(d.getMinutes())+" GMT"+b}}}}function hatta_edit(){var b=
document.getElementById('editortext');if(b){var c=0+
document.location.hash.substring(1);var d=b.textContent.match(/(.*\n)/g);var
f='';for(var i=0;i<d.length&&i<c;++i){f+=d[i]}b.focus();if(b.setSelectionRange)
{b.setSelectionRange(f.length,f.length)}else if(b.createTextRange){var g=
b.createTextRange();g.collapse(true);g.moveEnd('character',f.length);
g.moveStart('character',f.length);g.select()}var h=document.createElement('pre'
);b.parentNode.appendChild(h);var k=window.getComputedStyle(b,'');h.style.font=
k.font;h.style.border=k.border;h.style.outline=k.outline;h.style.lineHeight=
k.lineHeight;h.style.letterSpacing=k.letterSpacing;h.style.fontFamily=
k.fontFamily;h.style.fontSize=k.fontSize;h.style.padding=0;h.style.overflow=
'scroll';try{h.style.whiteSpace="-moz-pre-wrap"}catch(e){};try{
h.style.whiteSpace="-o-pre-wrap"}catch(e){};try{h.style.whiteSpace="-pre-wrap"
}catch(e){};try{h.style.whiteSpace="pre-wrap"}catch(e){};h.textContent=f;
b.scrollTop=h.scrollHeight;h.parentNode.removeChild(h)}else{var l='';var m=
document.getElementsByTagName('link');for(var i=0;i<m.length;++i){var n=m[i];
if(n.getAttribute('type')==='application/wiki'){l=n.getAttribute('href')}}if(
l===''){return}var o=['p','h1','h2','h3','h4','h5','h6','pre','ul','div',
'span'];for(var j=0;j<o.length;++j){var m=document.getElementsByTagName(o[j]);
for(var i=0;i<m.length;++i){var n=m[i];if(n.id&&n.id.match(/^line_\d+$/)){
n.ondblclick=function(){var a=l+'#'+this.id.replace('line_','');
document.location.href=a}}}}}}
window.onload=function(){hatta_dates();hatta_edit()}"""
    style = """\
html { background: #fff; color: #2e3436;
    font-family: sans-serif; font-size: 96% }
body { margin: 1em auto; line-height: 1.3; width: 40em }
a { color: #3465a4; text-decoration: none }
a:hover { text-decoration: underline }
a.wiki:visited { color: #204a87 }
a.nonexistent, a.nonexistent:visited { color: #a40000; }
a.external { color: #3465a4; text-decoration: underline }
a.external:visited { color: #75507b }
a img { border: none }
img.math, img.smiley { vertical-align: middle }
pre { font-size: 100%; white-space: pre-wrap; word-wrap: break-word;
    white-space: -moz-pre-wrap; white-space: -pre-wrap;
    white-space: -o-pre-wrap; line-height: 1.2; color: #555753 }
div.conflict pre.local { background: #fcaf3e; margin-bottom: 0; color: 000}
div.conflict pre.other { background: #ffdd66; margin-top: 0; color: 000; border-top: #d80 dashed 1px; }
pre.diff div.orig { font-size: 75%; color: #babdb6 }
b.highlight, pre.diff ins { font-weight: bold; background: #fcaf3e;
color: #ce5c00; text-decoration: none }
pre.diff del { background: #eeeeec; color: #888a85; text-decoration: none }
pre.diff div.change { border-left: 2px solid #fcaf3e }
div.footer { border-top: solid 1px #babdb6; text-align: right }
h1, h2, h3, h4 { color: #babdb6; font-weight: normal; letter-spacing: 0.125em}
div.buttons { text-align: center }
input.button, div.buttons input { font-weight: bold; font-size: 100%;
    background: #eee; border: solid 1px #babdb6; margin: 0.25em; color: #888a85}
.history input.button { font-size: 75% }
.editor textarea { width: 100%; display: block; font-size: 100%;
    border: solid 1px #babdb6; }
.editor label { display:block; text-align: right }
.editor .upload { margin: 2em auto; text-align: center }
form.search input.search, .editor label input { font-size: 100%;
    border: solid 1px #babdb6; margin: 0.125em 0 }
.editor label.comment input  { width: 32em }
a.logo { float: left; display: block; margin: 0.25em }
div.header h1 { margin: 0; }
div.content { clear: left }
form.search { margin:0; text-align: right; font-size: 80% }
div.snippet { font-size: 80%; color: #888a85 }
div.header div.menu { float: right; margin-top: 1.25em }
div.header div.menu a.current { color: #000 }
hr { background: transparent; border:none; height: 0;
     border-bottom: 1px solid #babdb6; clear: both }
blockquote { border-left:.25em solid #ccc; padding-left:.5em; margin-left:0}
abbr.date {border:none}
dt {font-weight: bold; float: left; }
dd {font-style: italic; }
"""

    def __init__(self, config):
        if config.get_bool('show_version', False):
            sys.stdout.write("Hatta %s\n" % __version__)
            sys.exit()
        self.dead = False
        self.config = config
        self.language = config.get('language', None)
        global _
        if self.language is not None:
            try:
                _ = gettext.translation('hatta', 'locale',
                                        languages=[self.language]).ugettext
            except IOError:
                _ = gettext.translation('hatta', fallback=True,
                                        languages=[self.language]).ugettext
        else:
            _ = gettext.translation('hatta', fallback=True).ugettext
        self._ = _
        self.path = os.path.abspath(config.get('pages_path', 'docs'))
        self.page_charset = config.get('page_charset', 'utf-8')
        self.menu_page = self.config.get('menu_page', u'Menu')
        self.front_page = self.config.get('front_page', u'Home')
        self.logo_page = self.config.get('logo_page', u'logo.png')
        self.locked_page = self.config.get('locked_page', u'Locked')
        self.site_name = self.config.get('site_name', u'Hatta Wiki')
        self.read_only = self.config.get_bool('read_only', False)
        self.icon_page = self.config.get('icon_page', None)
        self.pygments_style = self.config.get('pygments_style', 'tango')
        self.subdirectories = self.config.get_bool('subdirectories', False)
        if self.subdirectories:
            self.storage = storage.WikiSubdirectoryStorage(self.path, self.page_charset, _)
        else:
            self.storage = self.storage_class(self.path, self.page_charset, _)
        self.cache = config.get('cache_path', None)
        if self.cache is None:
            self.cache = os.path.join(self.storage.repo_path, '.hg', 'hatta', 'cache')
        self.cache = os.path.abspath(self.cache)
        if not os.path.isdir(self.cache):
            os.makedirs(self.cache)
#            reindex = True
#        else:
#            reindex = False
        self.index = self.index_class(self.cache, self.language, self.storage, _)
        self.url_rules = URL.rules(self)
        self.url_map = werkzeug.routing.Map(self.url_rules, converters={
            'title':WikiTitleConverter,
            'all':WikiAllConverter
        })

    def add_url_rule(self, rule):
        """Let plugins add additional url rules."""

        self.url_rules.append(rule)
        self.url_map = werkzeug.routing.Map(self.url_rules, converters={
            'title':WikiTitleConverter,
            'all':WikiAllConverter
        })

    def get_page(self, request, title):
        """Creates a page object based on page's mime type"""

        if title:
            try:
                page_class, mime = self.filename_map[title]
            except KeyError:
                mime = page_mime(title)
                major, minor = mime.split('/', 1)
                try:
                    page_class = self.mime_map[mime]
                except KeyError:
                    try:
                        plus_pos = minor.find('+')
                        if plus_pos>0:
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
            page_class = page.WikiPage
            mime = ''
        return page_class(self, request, title, mime)

    def response(self, request, title, content, etag='', mime='text/html',
                 rev=None, size=None):
        """Create a WikiResponse for a page."""

        response = WikiResponse(content, mimetype=mime)
        if rev is None:
            inode, _size, mtime = self.storage.page_file_meta(title)
            response.set_etag(u'%s/%s/%d-%d' % (etag, werkzeug.url_quote(title),
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
        response = werkzeug.Response(content, mimetype=mime)
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
        html = page.render_content(content)
        dependencies = page.dependencies()
        etag = '/(%s)' % u','.join(dependencies)
        return self.response(request, title, html, etag=etag)

    @URL('/+history/<title:title>/<int:rev>')
    def revision(self, request, title, rev):
        text = self.storage.revision_text(title, rev)
        link = werkzeug.html.a(werkzeug.html(title),
                               href=request.get_url(title))
        content = [
            werkzeug.html.p(
                werkzeug.html(
                    _(u'Content of revision %(rev)d of page %(title)s:'))
                % {'rev': rev, 'title': link }),
            werkzeug.html.pre(werkzeug.html(text)),
        ]
        special_title = _(u'Revision of "%(title)s"') % {'title': title}
        page = self.get_page(request, title)
        html = page.render_content(content, special_title)
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
        return werkzeug.Response('%d' % version, mimetype="text/plain")

    @URL('/+edit/<title:title>', methods=['POST'])
    def save(self, request, title):
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
            self.index.update(self, request)
            page = self.get_page(request, title)
            if text is not None:
                if title == self.locked_page:
                    for link, label in page.extract_links(text):
                        if title == link:
                            raise ForbiddenErr(
                                _(u"This page is locked."))
                if u'href="' in comment or u'http:' in comment:
                    raise ForbiddenErr()
                if text.strip() == '':
                    self.storage.delete_page(title, author, comment)
                    url = request.get_url(self.front_page)
                else:
                    self.storage.save_text(title, text, author, comment, parent)
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
        content = page.editor_form(preview)
        special_title = _(u'Editing "%(title)s"') % {'title': title}
        html = page.render_content(content, special_title)
        if not exists:
            response = werkzeug.Response(html, mimetype="text/html",
                                     status='404 Not found')

        elif preview:
            response = werkzeug.Response(html, mimetype="text/html")
        else:
            response = self.response(request, title, html, '/edit')
        response.headers.add('Cache-Control', 'no-cache')
        return response

    @URL('/+feed/atom')
    @URL('/+feed/rss')
    def atom(self, request):
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
            if rev>0:
                url = request.adapter.build(self.diff, {
                    'title': title,
                    'from_rev': rev-1,
                    'to_rev': rev
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

        mime = page_mime(title)
        if mime == 'text/x-wiki':
            mime = 'text/plain'
        try:
            wrap_file = werkzeug.wrap_file
        except AttributeError:
            wrap_file = lambda x, y:y
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
            wrap_file = lambda x, y:y
        f = wrap_file(request.environ, open(cache_file))
        response = self.response(request, title, f, '/render', cache_mime,
                                 size=cache_size)
        response.direct_passthrough = True
        return response

    @URL('/+undo/<title:title>', methods=['POST'])
    def undo(self, request, title):
        """Revert a change to a page."""

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
            self.index.update(self, request)
            if rev == 0:
                comment = _(u'Delete page %(title)s') % {'title': title}
                data = ''
                self.storage.delete_page(title, author, comment)
            else:
                comment = _(u'Undo of change %(rev)d of page %(title)s') % {
                    'rev': rev, 'title': title}
                data = self.storage.page_revision(title, rev-1)
                self.storage.save_data(title, data, author, comment, parent)
            page = self.get_page(request, title)
            self.index.update_page(page, title, data=data)
        url = request.adapter.build(self.history, {'title': title},
                                    method='GET', force_external=True)
        return werkzeug.redirect(url, 303)

    @URL('/+history/<title:title>')
    def history(self, request, title):
        """Display history of changes of a page."""

        page = self.get_page(request, title)
        content = page.render_content(page.history_list(),
            _(u'History of "%(title)s"') % {'title': title})
        response = self.response(request, title, content, '/history')
        return response

    @URL('/+history/')
    def recent_changes(self, request):
        """Serve the recent changes page."""

        def changes_list(page):
            """Generate the content of the recent changes page."""

            h = werkzeug.html
            yield u'<ul>'
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
                        'from_rev': rev-1,
                        'to_rev': lastrev.get(title, rev)
                    })
                elif rev == 0:
                    date_url = request.adapter.build(self.revision, {
                        'title': title, 'rev': rev})
                else:
                    date_url = request.adapter.build(self.history, {
                        'title': title})
                last[title] = author, comment
                lastrev[title] = rev

                yield h.li(h.a(page.date_html(date), href=date_url), ' ',
                    h.b(page.wiki_link(title)), u' . . . . ',
                    h.i(page.wiki_link('~%s' % author, author)),
                    h.div(h(comment), class_="comment")
                )
            yield u'</ul>'

        page = self.get_page(request, '')
        content = page.render_content(changes_list(page), _(u'Recent changes'))
        response = WikiResponse(content, mimetype='text/html')
        response.set_etag('/history/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    @URL('/+history/<title:title>/<int:from_rev>:<int:to_rev>')
    def diff(self, request, title, from_rev, to_rev):
        """Show the differences between specified revisions."""

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
        html = page.render_content(content, special_title)
        response = werkzeug.Response(html, mimetype='text/html')
        return response


    @URL('/+index')
    def all_pages(self, request):
        """Show index of all pages in the wiki."""

        page = self.get_page(request, '')
        all_pages = sorted(self.storage.all_pages())
        content = page.pages_list(all_pages, _(u'Index of all pages'))
        html = page.render_content(content, _(u'Page Index'))
        response = WikiResponse(html, mimetype='text/html')
        response.set_etag('/+index/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    @URL('/+orphaned')
    def orphaned(self, request):
        """Show all pages that don't have backlinks."""

        page = self.get_page(request, '')
        pages = self.index.orphaned_pages()
        content = page.pages_list(pages,
                                  _(u'List of pages with no links to them'))
        html = page.render_content(content, _(u'Orphaned pages'))
        response = WikiResponse(html, mimetype='text/html')
        response.set_etag('/+orphaned/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    @URL('/+wanted')
    def wanted(self, request):
        """Show all pages that don't exist yet, but are linked."""

        def wanted_pages_list(page):
            """Generate the content of wanted pages page."""

            h = werkzeug.html
            yield h.p(h(
                _(u"List of pages that are linked to, but don't exist yet.")))
            yield u'<ol class="wanted">'
            for refs, title in self.index.wanted_pages():
                url = page.get_url(title, self.backlinks)
                yield h.li(h.b(page.wiki_link(title)),
                           h.i(u' (', h.a(h(_(u"%d references") % refs),
                                          href=url, class_="backlinks"), ')'))
            yield u'</ol>'

        page = self.get_page(request, '')
        content = wanted_pages_list(page)
        html = page.render_content(content, _(u'Wanted pages'))
        response = WikiResponse(html, mimetype='text/html')
        response.set_etag('/+wanted/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    @URL('/+search', methods=['GET', 'POST'])
    def search(self, request):
        """Serve the search results page."""

        def search_snippet(title, words):
            """Extract a snippet of text for search results."""

            try:
                text = self.storage.page_text(title)
            except error.NotFoundErr:
                return u''
            regexp = re.compile(u"|".join(re.escape(w) for w in words),
                                re.U|re.I)
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
            self.index.update(self, request)
            result = sorted(self.index.find(words), key=lambda x:-x[0])
            yield werkzeug.html.p(h(_(u'%d page(s) containing all words:')
                                  % len(result)))
            yield u'<ol class="search">'
            for number, (score, title) in enumerate(result):
                yield h.li(h.b(page.wiki_link(title)), u' ', h.i(str(score)),
                           h.div(search_snippet(title, words),
                                 _class="snippet"),
                           id_="search-%d" % (number+1))
            yield u'</ol>'

        query = request.values.get('q', u'').strip()
        page = self.get_page(request, '')
        if not query:
            url = request.get_url(view=self.all_pages, external=True)
            return werkzeug.routing.redirect(url, code=303)
        words = tuple(self.index.split_text(query, stop=False))
        if not words:
            words = (query,)
        title = _(u'Searching for "%s"') % u" ".join(words)
        content = page_search(words, page, request)
        html = page.render_content(content, title)
        return WikiResponse(html, mimetype='text/html')

    @URL('/+search/<title:title>', methods=['GET', 'POST'])
    def backlinks(self, request, title):
        """Serve the page with backlinks."""

        self.storage.reopen()
        self.index.update(self, request)
        page = self.get_page(request, title)
        message = _(u'Pages that contain a link to %(link)s.')
        link = page.wiki_link(title)
        pages = self.index.page_backlinks(title)
        content = page.pages_list(pages, message, link, _class='backlinks')
        html = page.render_content(content, _(u'Links to "%s"') % title)
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

        if pygments is None:
            raise NotImplementedErr(_(u"Code highlighting is not available."))

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
                  'Disallow: /+hg\r\n'
                 )
        return self._serve_default(request, 'robots.txt', robots,
                                   'text/plain')

    @URL('/+hg<all:path>', methods=['GET', 'POST', 'HEAD'])
    def hgweb(self, request, path=None):
        """Serve the pages repository on the web like a normal hg repository."""

        if not self.config.get_bool('hgweb', False):
            raise ForbiddenErr(_(u'Repository access disabled.'))
        app = mercurial.hgweb.request.wsgiapplication(
            lambda: mercurial.hgweb.hgweb(self.storage.repo, self.site_name))
        def hg_app(env, start):
            env = request.environ
            prefix='/+hg'
            if env['PATH_INFO'].startswith(prefix):
                env["PATH_INFO"] = env["PATH_INFO"][len(prefix):]
                env["SCRIPT_NAME"] += prefix
            return app(env, start)
        return hg_app

    @URL('/off-with-his-head', methods=['GET'])
    def die(self, request):
        """Terminate the standalone server if invoked from localhost."""

        if not request.remote_addr.startswith('127.'):
            raise ForbiddenErr(_(u'This URL can only be called locally.'))
        def agony():
            yield u'Oh dear!'
            self.dead = True
        return werkzeug.Response(agony(), mimetype='text/plain')

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

