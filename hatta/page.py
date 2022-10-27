#!/usr/bin/python
# -*- coding: utf-8 -*-

import difflib
import hashlib
import io
import mimetypes
import os
import re

from werkzeug.urls import url_quote, url_fix
from markupsafe import escape, Markup
from dominate import tags


tags.html_tag.__html__ = tags.html_tag.render

pygments = None
try:
    import pygments
    import pygments.formatters
    import pygments.lexers

    class WikiWrapFormatter(pygments.formatters.HtmlFormatter):
        def wrapper(self, source, *args):
            """Wrap each line of formatted output."""

            yield 0, '<div class="highlight"><pre>'
            for lineno, line in source:
                yield (lineno,
                       Markup(tags.span(line, id_="line_%d" %
                                         formatter.line_no)))
                formatter.line_no += 1
            yield 0, '</pre></div>'

except ImportError:
    pass

captcha = None
try:
    from recaptcha.client import captcha
except ImportError:
    pass

Image = None
try:
    from PIL import Image
except ImportError:
    pass

import hatta.error
import hatta.parser


def check_lock(wiki, title):
    _ = wiki.gettext
    restricted_pages = [
        'scripts.js',
        'robots.txt',
    ]
    if wiki.read_only:
        raise hatta.error.ForbiddenErr(_("This site is read-only."))
    if title in restricted_pages:
        raise hatta.error.ForbiddenErr(_("""Can't edit this page.
It can only be edited by the site admin directly on the disk."""))
    if title in wiki.index.page_links(wiki.locked_page, wiki):
        raise hatta.error.ForbiddenErr(_("This page is locked."))



def get_page(request, title, wiki=None):
    """Creates a page object based on page's mime type"""

    if wiki is None:
        wiki = request.wiki
    if title:
        try:
            page_class, mime = wiki.filename_map[title]
        except KeyError:
            mime = page_mime(title)
            major, minor = mime.split('/', 1)
            try:
                page_class = wiki.mime_map[mime]
            except KeyError:
                try:
                    plus_pos = minor.find('+')
                    if plus_pos > 0:
                        minor_base = minor[plus_pos:]
                    else:
                        minor_base = ''
                    base_mime = '/'.join([major, minor_base])
                    page_class = wiki.mime_map[base_mime]
                except KeyError:
                    try:
                        page_class = wiki.mime_map[major]
                    except KeyError:
                        page_class = wiki.mime_map['']
    else:
        page_class = WikiPageSpecial
        mime = ''
    return page_class(wiki, request, title, mime)


def page_mime(title):
    """
    Guess page's mime type based on corresponding file name.
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

    addr = title #.encode('utf-8')  # the encoding doesn't relly matter here
    mime, encoding = mimetypes.guess_type(addr, strict=False)
    if encoding:
        mime = 'archive/%s' % encoding
    if mime is None:
        mime = 'text/x-wiki'
    return mime


def date_html(date_time):
    """
    Create HTML for a date, according to recommendation at
    http://microformats.org/wiki/date
    """

    return date_time.strftime(
        '<abbr class="date" title="%Y-%m-%dT%H:%M:%SZ">%Y-%m-%d %H:%M</abbr>')


class WikiPage(object):
    """Everything needed for rendering a page."""

    def __init__(self, wiki, request, title, mime):
        self.request = request
        self.title = title
        self.mime = mime
        # for now we just use the globals from wiki object
        if request:
            self.get_url = request.get_url
            self.get_download_url = request.get_download_url
        self.wiki = wiki
        self.storage = self.wiki.storage
        self.index = self.wiki.index
        self.config = self.wiki.config
        if self.wiki.alias_page and self.wiki.alias_page in self.storage:
            self.aliases = dict(
                self.index.page_links_and_labels(self.wiki.alias_page, wiki=self.wiki))
        else:
            self.aliases = {}
        self._revision = None

    @property
    def revision(self):
        if self._revision is None:
            self._revision = self.storage.get_revision(self.title)
        return self._revision

    def link_alias(self, addr):
        """Find a target address for an alias."""

        try:
            alias, target = addr.split(':', 1)
        except ValueError:
            return self.wiki.alias_page
        try:
            pattern = self.aliases[alias]
        except KeyError:
            return self.wiki.alias_page
        try:
            link = pattern % target
        except TypeError:
            link = pattern + target
        return link

    def wiki_link(self, addr, label=None, class_=None, image=None, lineno=0):
        """Create HTML for a wiki link."""

        addr = addr.strip()
        text = escape(label or addr)
        chunk = ''
        if class_ is not None:
            classes = [class_]
        else:
            classes = []
        if hatta.parser.external_link(addr):
            classes.append('external')
            if addr.startswith('mailto:'):
                # Obfuscate e-mails a little bit.
                classes.append('mail')
                text = text.replace('@', '&#64;').replace('.', '&#46;')
                href = escape(addr).replace('@', '%40').replace('.', '%2E')
            else:
                href = escape(url_fix(addr))
        else:
            if '#' in addr:
                addr, chunk = addr.split('#', 1)
                chunk = '#' + url_fix(chunk)
            if addr.startswith(':'):
                alias = self.link_alias(addr[1:])
                href = escape(url_fix(alias) + chunk)
                classes.append('external')
                classes.append('alias')
            elif addr.startswith('+'):
                href = '/'.join([self.request.script_root,
                                 '+' + escape(addr[1:])])
                classes.append('special')
            elif addr == '':
                href = escape(chunk)
                classes.append('anchor')
            else:
                classes.append('wiki')
                href = escape(self.get_url(addr) + chunk)
                if addr not in self.storage:
                    classes.append('nonexistent')
        class_ = escape(' '.join(classes) or '')
        link = Markup(tags.a(image or text, href=href, _class=class_, title=escape(addr + chunk)))
        return link

    def wiki_image(self, addr, alt, class_='wiki', lineno=0):
        """Create HTML for a wiki image."""

        addr = addr.strip()
        chunk = ''
        if hatta.parser.external_link(addr):
            return tags.img(src=url_fix(addr), class_="external",
                            alt=alt)
        if '#' in addr:
            addr, chunk = addr.split('#', 1)
        if addr == '':
            return tags.a(name=chunk)
        elif addr.startswith(':'):
            if chunk:
                chunk = '#' + chunk
            alias = self.link_alias(addr[1:])
            href = url_fix(alias + chunk)
            return tags.img(src=href, class_="external alias", alt=alt)
        elif addr in self.storage:
            mime = page_mime(addr)
            if mime.startswith('image/'):
                return tags.img(src=self.get_download_url(addr), class_=class_,
                                alt=alt)
            else:
                return tags.img(href=self.get_download_url(addr), alt=alt)
        else:
            return tags.a(Markup(alt), href=self.get_url(addr))

    def menu(self):
        """Generate the menu items"""
        _ = self.wiki.gettext
        if self.wiki.menu_page in self.storage:
            items = self.index.page_links_and_labels(self.wiki.menu_page, wiki=self.wiki)
        else:
            items = [
                (self.wiki.front_page, self.wiki.front_page),
                ('+history/', _('Recent changes')),
            ]
        for link, label in items:
            if link == self.title:
                class_ = "current"
            else:
                class_ = None
            yield self.wiki_link(link, label, class_=class_)

    def template(self, template_name, **kwargs):
        template = self.wiki.template_env.get_template(template_name)
        edit_url = None
        if self.title:
            try:
                check_lock(self.wiki, self.title)
                edit_url = self.get_url(self.title, 'edit')
            except hatta.error.ForbiddenErr:
                pass
        context = {
            'request': self.request,
            'wiki': self.wiki,
            'title': self.title,
            'title_quoted': url_quote(self.title, safe=''),
            'mime': self.mime,
            'url': self.get_url,
            'download_url': self.get_download_url,
            'config': self.config,
            'page': self,
            'edit_url': edit_url,
        }
        context.update(kwargs)
        stream = template.stream(**context)
        stream.enable_buffering(10)
        return stream

    def dependencies(self):
        """Refresh the page when any of those pages was changed."""

        dependencies = set()
        for title in [self.wiki.logo_page, self.wiki.menu_page]:
            if title not in self.storage:
                dependencies.add(url_quote(title))
        for title in [self.wiki.menu_page]:
            if title in self.storage:
                nrev = self.storage.get_revision(title)
                etag = '%s/%s-%s' % (url_quote(title), nrev.rev, nrev.date.isoformat())
                dependencies.add(etag)
        return dependencies

    def get_edit_help(self):
        page = get_page(self.request, self.wiki.help_page)
        try:
            return ''.join(page.view_content())
        except hatta.error.NotFoundErr:
            return ''

    def render_editor(self, preview=None, captcha_error=None):
        _ = self.wiki.gettext
        author = self.request.get_author()
        if self.title in self.storage:
            comment = _('changed')
            rev = self.revision.rev
            old_author = self.revision.author
            old_comment = self.revision.comment
            if old_author == author:
                comment = old_comment
        else:
            comment = _('uploaded')
            rev = -1
        if captcha and self.wiki.recaptcha_public_key:
            recaptcha_html = captcha.displayhtml(
                    self.wiki.recaptcha_public_key, error=captcha_error)
        else:
            recaptcha_html = None
        context = {
            'comment': comment,
            'author': author,
            'parent': rev,
            'recaptcha_html': recaptcha_html,
            'help': self.get_edit_help(),
        }
        return self.template('edit_file.html', **context)


class WikiPageSpecial(WikiPage):
    """Special pages, like recent changes, index, etc."""


class WikiPageText(WikiPage):
    """Pages of mime type text/* use this for display."""

    def content_iter(self, lines):
        yield '<pre>'
        for line in lines:
            yield Markup(line)
        yield '</pre>'

    def plain_text(self):
        """
        Get the content of the page with all markup removed, used for
        indexing.
        """

        return self.revision.text

    def view_content(self, lines=None):
        """
        Read the page content from storage or preview and return iterator.
        """

        if lines is None:
            lines = self.revision.text.splitlines(True)
        return self.content_iter(lines)

    def render_editor(self, preview=None, captcha_error=None):
        """Generate the HTML for the editor."""

        _ = self.wiki.gettext
        author = self.request.get_author()
        lines = []
        try:
            lines = self.revision.text.splitlines(True)
            rev = self.revision.rev
            old_author = self.revision.author
            old_comment = self.revision.comment
            comment = _('modified')
            if old_author == author:
                comment = old_comment
        except hatta.error.NotFoundErr:
            comment = _('created')
            rev = -1
        except hatta.error.ForbiddenErr as e:
            return tags.p(Markup(str(e)))
        if preview:
            lines = preview
            comment = self.request.form.get('comment', comment)
        if captcha and self.wiki.recaptcha_public_key:
            recaptcha_html = captcha.displayhtml(
                    self.wiki.recaptcha_public_key, error=captcha_error)
        else:
            recaptcha_html = None
        context = {
            'comment': comment,
            'preview': preview,
            'recaptcha_html': recaptcha_html,
            'help': self.get_edit_help(),
            'author': author,
            'parent': rev,
            'lines': lines,
        }
        return self.template('edit_text.html', **context)

    def diff_content(self, from_text, to_text, message=''):
        """Generate the HTML markup for a diff."""

        def infiniter(iterator):
            """Turn an iterator into an infinite one, padding it with None"""

            for i in iterator:
                yield i
            while True:
                yield None

        diff = difflib._mdiff(from_text.split('\n'), to_text.split('\n'))
        mark_re = re.compile('\0[-+^]([^\1\0]*)\1|([^\0\1])')
        yield message
        yield '<pre class="diff">'
        for old_line, new_line, changed in diff:
            old_no, old_text = old_line
            new_no, new_text = new_line
            line_no = (new_no or old_no or 1) - 1
            if changed:
                yield '<div class="change" id="line_%d">' % line_no
                old_iter = infiniter(mark_re.finditer(old_text))
                new_iter = infiniter(mark_re.finditer(new_text))
                old = next(old_iter)
                new = next(new_iter)
                buff = ''
                while old or new:
                    while old and old.group(1):
                        if buff:
                            yield escape(buff)
                            buff = ''
                        yield '<del>%s</del>' % escape(old.group(1))
                        old = next(old_iter)
                    while new and new.group(1):
                        if buff:
                            yield escape(buff)
                            buff = ''
                        yield '<ins>%s</ins>' % escape(new.group(1))
                        new = next(new_iter)
                    if new:
                        buff += new.group(2)
                    old = next(old_iter)
                    new = next(new_iter)
                if buff:
                    yield escape(buff)
                yield '</div>'
            else:
                yield '<div class="orig" id="line_%d">%s</div>' % (
                    line_no, escape(old_text))
        yield '</pre>'


class WikiPageColorText(WikiPageText):
    """Text pages, but displayed colorized with pygments"""

    def view_content(self, lines=None):
        """Generate HTML for the content."""

        if lines is None:
            text = self.revision.text
        else:
            text = ''.join(lines)
        return self.highlight(text, mime=self.mime)

    def highlight(self, text, mime=None, syntax=None, line_no=0):
        """Colorize the source code."""

        if pygments is None:
            yield Markup(tags.pre(text))
            return

        formatter = WikiWrapFormatter()
        formatter.line_no = line_no


        try:
            if mime:
                lexer = pygments.lexers.get_lexer_for_mimetype(mime)
            elif syntax:
                lexer = pygments.lexers.get_lexer_by_name(syntax)
            else:
                lexer = pygments.lexers.guess_lexer(text)
        except:
            yield tags.pre(Markup(text))
            return
        yield pygments.highlight(text, lexer, formatter, outfile=None)


class WikiPageWiki(WikiPageColorText):
    """Pages of with wiki markup use this for display."""

    def __init__(self, *args, **kw):
        super(WikiPageWiki, self).__init__(*args, **kw)
        if self.config.get_bool('wiki_words', False):
            self.parser = hatta.parser.WikiWikiParser
        else:
            self.parser = hatta.parser.WikiParser
        if self.config.get_bool('ignore_indent', False):
            try:
                del self.parser.block['indent']
            except KeyError:
                pass

    def extract_links(self, text=None):
        """Extract all links from the page."""

        if text is None:
            try:
                text = self.revision.text
            except hatta.error.NotFoundErr:
                text = ''
        return self.parser.extract_links(text)

    def view_content(self, lines=None):
        if self.wiki.cache and not lines and self.revision:
            cache_key = '%s:%s' % (hashlib.md5(self.title.encode('utf8')).hexdigest(), self.revision.rev)
            cached = self.wiki.cache.get(cache_key)
        else:
            cache_key = None
            cached = None
        if not cached:
            if lines is None:
                if self.revision is None:
                    raise hatta.error.NotFoundErr()
                lines = self.revision.text.splitlines(True)
            if self.wiki.icon_page and self.wiki.icon_page in self.storage:
                icons = self.index.page_links_and_labels(self.wiki.icon_page, wiki=self.wiki)
                smilies = dict((emo, link) for (link, emo) in icons)
            else:
                smilies = None
            content = self.parser(lines, self.wiki_link, self.wiki_image,
                                 self.highlight, self.wiki_math, smilies)
            cached = list(content)
            if cache_key:
                self.wiki.cache.set(cache_key, cached, timeout=86400)
        return cached

    def wiki_math(self, math_text, display=False):
        math_url = self.wiki.math_url
        if math_url == '':
            return escape(math_text)
        elif math_url == 'mathjax':
            if display:
                return escape("$$\n%s\n$$" % math_text)
            else:
                return escape("$%s$" % math_text)
        if '%s' in math_url:
            url = math_url % url_quote(math_text)
        else:
            url = '%s%s' % (math_url, url_quote(math_text))
        label = escape(math_text)
        return tags.img(src=url, alt=label, class_="math")

    def dependencies(self):
        dependencies = WikiPage.dependencies(self)
        for title in [self.wiki.icon_page, self.wiki.alias_page]:
            if title in self.storage:
                trev = self.storage.get_revision(title)
                etag = '%s/%s-%s' % (url_quote(title), trev.rev, trev.date.isoformat())
                dependencies.add(etag)
        for link in self.index.page_links(self.title, wiki=self.wiki):
            if link not in self.storage:
                dependencies.add(url_quote(link))
        return dependencies


class WikiPageFile(WikiPage):
    """Pages of all other mime types use this for display."""

    def view_content(self, lines=None):
        if self.title not in self.storage:
            raise hatta.error.NotFoundErr()
        content = ['<p>Download <a href="%s">%s</a> as <i>%s</i>.</p>' %
                   (self.request.get_download_url(self.title),
                    escape(self.title), self.mime)]
        return content


class WikiPageImage(WikiPageFile):
    """Pages of mime type image/* use this for display."""

    def view_content(self, lines=None):
        if self.title not in self.storage:
            raise hatta.error.NotFoundErr()
        content = ['<a href="%s"><img src="%s" alt="%s"></a>'
                   % (self.request.get_url(self.title, 'download'),
                      self.request.get_url(self.title, 'render'),
                      escape(self.title))]
        return content

    @property
    def render_size(self):
        try:
            width = min(int(self.request.values.get('w', '512').strip()), 2048)
            height = min(int(self.request.values.get('h', '512').strip()), 2048)
        except ValueError:
            width = height = 512
        return width, height

    @property
    def render_file(self):
        return '%sx%x.png' % self.render_size

    def render_mime(self):
        """Give the filename and mime type of the rendered thumbnail."""

        if not Image:
            raise NotImplementedError('No Image library available')
        return  self.render_file, 'image/png'

    def render_cache(self):
        """Render the thumbnail and return the date."""

        if not Image:
            raise NotImplementedError('No Image library available')
        page_file = self.revision.file
        cache_file = io.BytesIO()
        with self.revision.file as page_file:
            try:
                im = Image.open(page_file)
                im = im.convert('RGBA')
                ow, oh = im.size
                nw, nh = self.render_size
                nw = min(nw, ow)
                nh = min(nh, oh)
                im.thumbnail((nw, nh), Image.ANTIALIAS)
                im.save(cache_file, 'PNG')
            except IOError:
                raise hatta.error.UnsupportedMediaTypeErr('Image corrupted')
        return cache_file.getvalue()


class WikiPageCSV(WikiPageFile):
    """Display class for type text/csv."""

    def content_iter(self, lines=None):
        import csv
        _ = self.wiki.gettext
        # XXX Add preview support
        reader = csv.reader(csv_file)
        html_title = escape(self.title)
        yield '<table id="%s" class="csvfile">' % html_title
        with self.revision.file as csv_file:
            try:
                for row in reader:
                    yield '<tr>%s</tr>' % (''.join('<td>%s</td>' % cell
                                                     for cell in row))
            except csv.Error as e:
                yield '</table>'
                yield tags.p(Markup(
                    _('Error parsing CSV file %{file}s on '
                      'line %{line}d: %{error}s') %
                    {'file': html_title, 'line': reader.line_num, 'error': e}))
        yield '</table>'

    def view_content(self, lines=None):
        if self.title not in self.storage:
            raise hatta.error.NotFoundErr()
        return self.content_iter(lines)


class WikiPageRST(WikiPageText):
    """
    Display ReStructured Text.
    """

    def content_iter(self, lines):
        try:
            from doccore import publish_parts
        except ImportError:
            return super(WikiPageRST, self).content_iter(lines)
        text = ''.join(lines)
        SAFE_DOCUTILS = dict(file_insertion_enabled=False, raw_enabled=False)
        content = publish_parts(text, writer_name='html',
                                settings_overrides=SAFE_DOCUTILS)['html_body']
        return [content]


class WikiPageBugs(WikiPageText):
    """
    Display class for type text/x-bugs
    Parse the ISSUES file in (roughly) format used by ciss
    """

    def content_iter(self, lines):
        last_lines = []
        in_header = False
        in_bug = False
        attributes = {}
        title = None
        for line_no, line in enumerate(lines):
            if last_lines and line.startswith('----'):
                title = ''.join(last_lines)
                last_lines = []
                in_header = True
                attributes = {}
            elif in_header and ':' in line:
                attribute, value = line.split(':', 1)
                attributes[attribute.strip()] = value.strip()
            else:
                if in_header:
                    if in_bug:
                        yield '</div>'
                    #tags = [tag.strip() for tag in
                    #        attributes.get('tags', '').split()
                    #        if tag.strip()]
                    yield '<div id="line_%d">' % (line_no)
                    in_bug = True
                    if title:
                        yield tags.h2(Markup(title))
                    if attributes:
                        yield '<dl>'
                        for attribute, value in attributes.items():
                            yield tags.dt(Markup(attribute))
                            yield tags.dd(Markup(value))
                        yield '</dl>'
                    in_header = False
                if not line.strip():
                    if last_lines:
                        if last_lines[0][0] in ' \t':
                            yield tags.pre(Markup(
                                            ''.join(last_lines)))
                        else:
                            yield tags.p(Markup(
                                            ''.join(last_lines)))
                        last_lines = []
                else:
                    last_lines.append(line)
        if last_lines:
            if last_lines[0][0] in ' \t':
                yield tags.pre(Markup(
                                ''.join(last_lines)))
            else:
                yield tags.p(Markup(
                                ''.join(last_lines)))
        if in_bug:
            yield '</div>'

filename_map = {
    'README': (WikiPageText, 'text/plain'),
    'ISSUES': (WikiPageBugs, 'text/x-bugs'),
    'ISSUES.txt': (WikiPageBugs, 'text/x-bugs'),
    'COPYING': (WikiPageText, 'text/plain'),
    'CHANGES': (WikiPageText, 'text/plain'),
    'MANIFEST': (WikiPageText, 'text/plain'),
    'favicon.ico': (WikiPageImage, 'image/x-icon'),
    'bulk.zip': (WikiPageFile, 'application/hatta+zip'),
}

mime_map = {
    'text': WikiPageColorText,
    'application/x-javascript': WikiPageColorText,
    'application/x-python': WikiPageColorText,
    'text/csv': WikiPageCSV,
    'text/x-rst': WikiPageRST,
    'text/x-wiki': WikiPageWiki,
    'image': WikiPageImage,
    '': WikiPageFile,
}

mimetypes.add_type('application/x-python', '.wsgi')
mimetypes.add_type('application/x-javascript', '.js')
mimetypes.add_type('text/x-rst', '.rst')
