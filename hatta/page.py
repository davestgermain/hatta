#!/usr/bin/python
# -*- coding: utf-8 -*-

import difflib
import mimetypes
import os
import re

import werkzeug
import werkzeug.contrib.atom

pygments = None
try:
    import pygments
    import pygments.formatters
    import pygments.lexers
    import pygments.styles
    import pygments.util
except ImportError:
    pass

captcha = None
try:
    from recaptcha.client import captcha
except ImportError:
    pass

Image = None
try:
    import Image
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
        raise hatta.error.ForbiddenErr(_(u"This site is read-only."))
    if title in restricted_pages:
        raise hatta.error.ForbiddenErr(_(u"""Can't edit this page.
It can only be edited by the site admin directly on the disk."""))
    if title in wiki.index.page_links(wiki.locked_page):
        raise hatta.error.ForbiddenErr(_(u"This page is locked."))



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

    addr = title.encode('utf-8')  # the encoding doesn't relly matter here
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
                self.index.page_links_and_labels(self.wiki.alias_page))
        else:
            self.aliases = {}

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
        text = werkzeug.escape(label or addr)
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
                href = werkzeug.escape(addr,
                    quote=True).replace('@', '%40').replace('.', '%2E')
            else:
                href = werkzeug.escape(werkzeug.url_fix(addr), quote=True)
        else:
            if '#' in addr:
                addr, chunk = addr.split('#', 1)
                chunk = '#' + werkzeug.url_fix(chunk)
            if addr.startswith(':'):
                alias = self.link_alias(addr[1:])
                href = werkzeug.escape(werkzeug.url_fix(alias) + chunk, True)
                classes.append('external')
                classes.append('alias')
            elif addr.startswith('+'):
                href = '/'.join([self.request.script_root,
                                 '+' + werkzeug.escape(addr[1:], quote=True)])
                classes.append('special')
            elif addr == u'':
                href = werkzeug.escape(chunk, True)
                classes.append('anchor')
            else:
                classes.append('wiki')
                href = werkzeug.escape(self.get_url(addr) + chunk, True)
                if addr not in self.storage:
                    classes.append('nonexistent')
        class_ = werkzeug.escape(' '.join(classes) or '', True)
        # We need to output HTML on our own to prevent escaping of href
        return '<a href="%s" class="%s" title="%s">%s</a>' % (
                href, class_, werkzeug.escape(addr + chunk, True),
                image or text)

    def wiki_image(self, addr, alt, class_='wiki', lineno=0):
        """Create HTML for a wiki image."""

        addr = addr.strip()
        html = werkzeug.html
        chunk = ''
        if hatta.parser.external_link(addr):
            return html.img(src=werkzeug.url_fix(addr), class_="external",
                            alt=alt)
        if '#' in addr:
            addr, chunk = addr.split('#', 1)
        if addr == '':
            return html.a(name=chunk)
        elif addr.startswith(':'):
            if chunk:
                chunk = '#' + chunk
            alias = self.link_alias(addr[1:])
            href = werkzeug.url_fix(alias + chunk)
            return html.img(src=href, class_="external alias", alt=alt)
        elif addr in self.storage:
            mime = page_mime(addr)
            if mime.startswith('image/'):
                return html.img(src=self.get_download_url(addr), class_=class_,
                                alt=alt)
            else:
                return html.img(href=self.get_download_url(addr), alt=alt)
        else:
            return html.a(html(alt), href=self.get_url(addr))

    def menu(self):
        """Generate the menu items"""
        _ = self.wiki.gettext
        if self.wiki.menu_page in self.storage:
            items = self.index.page_links_and_labels(self.wiki.menu_page)
        else:
            items = [
                (self.wiki.front_page, self.wiki.front_page),
                ('+history', _(u'Recent changes')),
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
                dependencies.add(werkzeug.url_quote(title))
        for title in [self.wiki.menu_page]:
            if title in self.storage:
                rev, date, author, comment = self.storage.page_meta(title)
                etag = '%s/%d-%s' % (werkzeug.url_quote(title), rev, date.isoformat())
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
            comment = _(u'changed')
            (rev, old_date, old_author,
                old_comment) = self.storage.page_meta(self.title)
            if old_author == author:
                comment = old_comment
        else:
            comment = _(u'uploaded')
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
            yield werkzeug.html(line)
        yield '</pre>'

    def plain_text(self):
        """
        Get the content of the page with all markup removed, used for
        indexing.
        """

        return self.storage.page_text(self.title)

    def view_content(self, lines=None):
        """
        Read the page content from storage or preview and return iterator.
        """

        if lines is None:
            lines = self.storage.page_text(self.title).splitlines(True)
        return self.content_iter(lines)

    def render_editor(self, preview=None, captcha_error=None):
        """Generate the HTML for the editor."""

        _ = self.wiki.gettext
        author = self.request.get_author()
        lines = []
        try:
            lines = self.storage.page_text(self.title).splitlines(True)
            (rev, old_date, old_author,
                old_comment) = self.storage.page_meta(self.title)
            comment = _(u'modified')
            if old_author == author:
                comment = old_comment
        except hatta.error.NotFoundErr:
            comment = _(u'created')
            rev = -1
        except hatta.error.ForbiddenErr, e:
            return werkzeug.html.p(werkzeug.html(unicode(e)))
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

    def diff_content(self, from_text, to_text, message=u''):
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
        yield u'<pre class="diff">'
        for old_line, new_line, changed in diff:
            old_no, old_text = old_line
            new_no, new_text = new_line
            line_no = (new_no or old_no or 1) - 1
            if changed:
                yield u'<div class="change" id="line_%d">' % line_no
                old_iter = infiniter(mark_re.finditer(old_text))
                new_iter = infiniter(mark_re.finditer(new_text))
                old = old_iter.next()
                new = new_iter.next()
                buff = u''
                while old or new:
                    while old and old.group(1):
                        if buff:
                            yield werkzeug.escape(buff)
                            buff = u''
                        yield u'<del>%s</del>' % werkzeug.escape(old.group(1))
                        old = old_iter.next()
                    while new and new.group(1):
                        if buff:
                            yield werkzeug.escape(buff)
                            buff = u''
                        yield u'<ins>%s</ins>' % werkzeug.escape(new.group(1))
                        new = new_iter.next()
                    if new:
                        buff += new.group(2)
                    old = old_iter.next()
                    new = new_iter.next()
                if buff:
                    yield werkzeug.escape(buff)
                yield u'</div>'
            else:
                yield u'<div class="orig" id="line_%d">%s</div>' % (
                    line_no, werkzeug.escape(old_text))
        yield u'</pre>'


class WikiPageColorText(WikiPageText):
    """Text pages, but displayed colorized with pygments"""

    def view_content(self, lines=None):
        """Generate HTML for the content."""

        if lines is None:
            text = self.storage.page_text(self.title)
        else:
            text = ''.join(lines)
        return self.highlight(text, mime=self.mime)

    def highlight(self, text, mime=None, syntax=None, line_no=0):
        """Colorize the source code."""

        if pygments is None:
            yield werkzeug.html.pre(werkzeug.html(text))
            return

        formatter = pygments.formatters.HtmlFormatter()
        formatter.line_no = line_no

        def wrapper(source, unused_outfile):
            """Wrap each line of formatted output."""

            yield 0, '<div class="highlight"><pre>'
            for lineno, line in source:
                yield (lineno,
                       werkzeug.html.span(line, id_="line_%d" %
                                         formatter.line_no))
                formatter.line_no += 1
            yield 0, '</pre></div>'

        formatter.wrap = wrapper
        try:
            if mime:
                lexer = pygments.lexers.get_lexer_for_mimetype(mime)
            elif syntax:
                lexer = pygments.lexers.get_lexer_by_name(syntax)
            else:
                lexer = pygments.lexers.guess_lexer(text)
        except pygments.util.ClassNotFoundErr:
            yield werkzeug.html.pre(werkzeug.html(text))
            return
        html = pygments.highlight(text, lexer, formatter)
        yield html


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
                text = self.storage.page_text(self.title)
            except hatta.error.NotFoundErr:
                text = u''
        return self.parser.extract_links(text)

    def view_content(self, lines=None):
        if lines is None:
            lines = self.storage.page_text(self.title).splitlines(True)
        if self.wiki.icon_page and self.wiki.icon_page in self.storage:
            icons = self.index.page_links_and_labels(self.wiki.icon_page)
            smilies = dict((emo, link) for (link, emo) in icons)
        else:
            smilies = None
        content = self.parser(lines, self.wiki_link, self.wiki_image,
                             self.highlight, self.wiki_math, smilies)
        return content

    def wiki_math(self, math_text, display=False):
        math_url = self.wiki.math_url
        if math_url == '':
            return werkzeug.escape(math_text)
        elif math_url == 'mathjax':
            if display:
                return werkzeug.escape(u"$$\n%s\n$$" % math_text)
            else:
                return werkzeug.escape(u"$%s$" % math_text)
        if '%s' in math_url:
            url = math_url % werkzeug.url_quote(math_text)
        else:
            url = '%s%s' % (math_url, werkzeug.url_quote(math_text))
        label = werkzeug.escape(math_text, quote=True)
        return werkzeug.html.img(src=url, alt=label, class_="math")

    def dependencies(self):
        dependencies = WikiPage.dependencies(self)
        for title in [self.wiki.icon_page, self.wiki.alias_page]:
            if title in self.storage:
                rev, date, author, comment = self.storage.page_meta(title)
                etag = '%s/%d-%s' % (werkzeug.url_quote(title), rev, date.isoformat())
                dependencies.add(etag)
        for link in self.index.page_links(self.title):
            if link not in self.storage:
                dependencies.add(werkzeug.url_quote(link))
        return dependencies


class WikiPageFile(WikiPage):
    """Pages of all other mime types use this for display."""

    def view_content(self, lines=None):
        if self.title not in self.storage:
            raise hatta.error.NotFoundErr()
        content = ['<p>Download <a href="%s">%s</a> as <i>%s</i>.</p>' %
                   (self.request.get_download_url(self.title),
                    werkzeug.escape(self.title), self.mime)]
        return content


class WikiPageImage(WikiPageFile):
    """Pages of mime type image/* use this for display."""

    render_file = '128x128.png'

    def view_content(self, lines=None):
        if self.title not in self.storage:
            raise hatta.error.NotFoundErr()
        content = ['<a href="%s"><img src="%s" alt="%s"></a>'
                   % (self.request.get_url(self.title, 'download'),
                      self.request.get_url(self.title, 'render'),
                      werkzeug.escape(self.title))]
        return content

    def render_mime(self):
        """Give the filename and mime type of the rendered thumbnail."""

        if not Image:
            raise NotImplementedError('No Image library available')
        return  self.render_file, 'image/png'

    def render_cache(self, cache_dir):
        """Render the thumbnail and save in the cache."""

        if not Image:
            raise NotImplementedError('No Image library available')
        page_file = self.storage.open_page(self.title)
        cache_path = os.path.join(cache_dir, self.render_file)
        cache_file = open(cache_path, 'wb')
        try:
            im = Image.open(page_file)
            im = im.convert('RGBA')
            im.thumbnail((128, 128), Image.ANTIALIAS)
            im.save(cache_file, 'PNG')
        except IOError:
            raise hatta.error.UnsupportedMediaTypeErr('Image corrupted')
        finally:
            cache_file.close()
        return cache_path


class WikiPageCSV(WikiPageFile):
    """Display class for type text/csv."""

    def content_iter(self, lines=None):
        import csv
        _ = self.wiki.gettext
        # XXX Add preview support
        csv_file = self.storage.open_page(self.title)
        reader = csv.reader(csv_file)
        html_title = werkzeug.escape(self.title, quote=True)
        yield u'<table id="%s" class="csvfile">' % html_title
        try:
            for row in reader:
                yield u'<tr>%s</tr>' % (u''.join(u'<td>%s</td>' % cell
                                                 for cell in row))
        except csv.Error, e:
            yield u'</table>'
            yield werkzeug.html.p(werkzeug.html(
                _(u'Error parsing CSV file %{file}s on '
                  u'line %{line}d: %{error}s') %
                {'file': html_title, 'line': reader.line_num, 'error': e}))
        finally:
            csv_file.close()
        yield u'</table>'

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
            from docutils.core import publish_parts
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
                        yield werkzeug.html.h2(werkzeug.html(title))
                    if attributes:
                        yield '<dl>'
                        for attribute, value in attributes.iteritems():
                            yield werkzeug.html.dt(werkzeug.html(attribute))
                            yield werkzeug.html.dd(werkzeug.html(value))
                        yield '</dl>'
                    in_header = False
                if not line.strip():
                    if last_lines:
                        if last_lines[0][0] in ' \t':
                            yield werkzeug.html.pre(werkzeug.html(
                                            ''.join(last_lines)))
                        else:
                            yield werkzeug.html.p(werkzeug.html(
                                            ''.join(last_lines)))
                        last_lines = []
                else:
                    last_lines.append(line)
        if last_lines:
            if last_lines[0][0] in ' \t':
                yield werkzeug.html.pre(werkzeug.html(
                                ''.join(last_lines)))
            else:
                yield werkzeug.html.p(werkzeug.html(
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
