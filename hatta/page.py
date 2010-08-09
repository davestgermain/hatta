#!/usr/bin/python
# -*- coding: utf-8 -*-

import difflib
import datetime
import mimetypes
import re

import werkzeug
import werkzeug.contrib.atom

try:
    import pygments
    import pygments.util
    import pygments.lexers
    import pygments.formatters
    import pygments.styles
except ImportError:
    pygments = None

try:
    import Image
except ImportError:
    Image = None

import parser
import error


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


class WikiPage(object):
    """Everything needed for rendering a page."""

    def __init__(self, wiki, request, title, mime):
        self.request = request
        self.title = title
        self.mime = mime
        # for now we just use the globals from wiki object
        self.get_url = self.request.get_url
        self.get_download_url = self.request.get_download_url
        self.wiki = wiki
        self.storage = self.wiki.storage
        self.index = self.wiki.index
        self.config = self.wiki.config

    def date_html(self, datetime):
        """
        Create HTML for a date, according to recommendation at
        http://microformats.org/wiki/date
        """

        text = datetime.strftime('%Y-%m-%d %H:%M')
        # We are going for YYYY-MM-DDTHH:MM:SSZ
        title = datetime.strftime('%Y-%m-%dT%H:%M:%SZ')
        html = werkzeug.html.abbr(text, class_="date", title=title)
        return html


    def wiki_link(self, addr, label=None, class_=None, image=None, lineno=0):
        """Create HTML for a wiki link."""

        addr = addr.strip()
        text = werkzeug.escape(label or addr)
        chunk = ''
        if class_ is not None:
            classes = [class_]
        else:
            classes = []
        if parser.external_link(addr):
            if addr.startswith('mailto:'):
                class_ = 'external email'
                text = text.replace('@', '&#64;').replace('.', '&#46;')
                href = addr.replace('@', '%40').replace('.', '%2E')
            else:
                classes.append('external')
                href = werkzeug.escape(addr, quote=True)
        else:
            if '#' in addr:
                addr, chunk = addr.split('#', 1)
                chunk = '#'+chunk
            if addr.startswith('+'):
                href = '/'.join([self.request.script_root,
                                 '+'+werkzeug.escape(addr[1:], quote=True)])
                classes.append('special')
            elif addr == u'':
                href = chunk
                classes.append('anchor')
            else:
                classes.append('wiki')
                href = self.get_url(addr) + chunk
                if addr not in self.storage:
                    classes.append('nonexistent')
        class_ = ' '.join(classes) or None
        return werkzeug.html.a(image or text, href=href, class_=class_,
                               title=addr+chunk)

    def wiki_image(self, addr, alt, class_='wiki', lineno=0):
        """Create HTML for a wiki image."""

        addr = addr.strip()
        html = werkzeug.html
        chunk = ''
        if parser.external_link(addr):
            return html.img(src=werkzeug.url_fix(addr), class_="external",
                            alt=alt)
        if '#' in addr:
            addr, chunk = addr.split('#', 1)
        if addr == '':
            return html.a(name=chunk)
        if addr in self.storage:
            mime = page_mime(addr)
            if mime.startswith('image/'):
                return html.img(src=self.get_download_url(addr), class_=class_,
                                alt=alt)
            else:
                return html.img(href=self.get_download_url(addr), alt=alt)
        else:
            return html.a(html(alt), href=self.get_url(addr))

    def search_form(self):
        html = werkzeug.html
        _ = self.wiki._
        return html.form(html.div(html.input(name="q", class_="search"),
                html.input(class_="button", type_="submit", value=_(u'Search')),
            ), method="GET", class_="search",
            action=self.get_url(None, self.wiki.search))

    def logo(self):
        html = werkzeug.html
        img = html.img(alt=u"[%s]" % self.wiki.front_page,
                       src=self.get_download_url(self.wiki.logo_page))
        return html.a(img, class_='logo', href=self.get_url(self.wiki.front_page))

    def menu(self):
        """Generate the menu items"""
        _ = self.wiki._
        if self.wiki.menu_page in self.storage:
            items = self.index.page_links_and_labels(self.wiki.menu_page)
        else:
            items = [
                (self.wiki.front_page, self.wiki.front_page),
                ('+history', _(u'Recent changes')),
            ]
        for link, label in items:
            if link == self.title:
                class_="current"
            else:
                class_ = None
            yield self.wiki_link(link, label, class_=class_)

    def header(self, special_title):
        html = werkzeug.html
        if self.wiki.logo_page in self.storage:
            yield self.logo()
        yield self.search_form()
        yield html.div(u" ".join(self.menu()), class_="menu")
        yield html.h1(html(special_title or self.title))

    def html_header(self, special_title, edit_url):
        e = lambda x: werkzeug.escape(x, quote=True)
        h = werkzeug.html
        yield h.title(u'%s - %s' % (e(special_title or self.title),
                                    e(self.wiki.site_name)))
        yield h.link(rel="stylesheet", type_="text/css",
                     href=self.get_url(None, self.wiki.pygments_css))
        yield h.link(rel="stylesheet", type_="text/css",
                     href=self.get_url(None, self.wiki.style_css))
        if special_title:
            yield h.meta(name="robots", content="NOINDEX,NOFOLLOW")
        if edit_url:
            yield h.link(rel="alternate", type_="application/wiki",
                         href=edit_url)
        yield h.link(rel="shortcut icon", type_="image/x-icon",
                     href=self.get_url(None, self.wiki.favicon_ico))
        yield h.link(rel="alternate", type_="application/rss+xml",
                     title=e("%s (ATOM)" % self.wiki.site_name),
                     href=self.get_url(None, self.wiki.atom))
        yield h.script(type_="text/javascript",
                     src=self.get_url(None, self.wiki.scripts_js))

    def footer(self, special_title, edit_url):
        _ = self.wiki._
        if special_title:
            footer_links = [
                (_(u'Changes'), 'changes',
                 self.get_url(None, self.wiki.recent_changes)),
                (_(u'Index'), 'index',
                 self.get_url(None, self.wiki.all_pages)),
                (_(u'Orphaned'), 'orphaned',
                 self.get_url(None, self.wiki.orphaned)),
                (_(u'Wanted'), 'wanted',
                 self.get_url(None, self.wiki.wanted)),
            ]
        else:
            footer_links = [
                (_(u'Edit'), 'edit', edit_url),
                (_(u'History'), 'history',
                 self.get_url(self.title, self.wiki.history)),
                (_(u'Backlinks'), 'backlinks',
                 self.get_url(self.title, self.wiki.backlinks))
            ]
        for label, class_, url in footer_links:
            if url:
                yield werkzeug.html.a(werkzeug.html(label), href=url,
                                      class_=class_)
                yield u'\n'

    def render_content(self, content, special_title=None):
        """The main page template."""

        edit_url = None
        if not special_title:
            try:
                self.wiki._check_lock(self.title)
                edit_url = self.get_url(self.title, self.wiki.edit)
            except ForbiddenErr:
                pass

        yield u"""\
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
"http://www.w3.org/TR/html4/strict.dtd">
<html><head>\n"""
        for part in self.html_header(special_title, edit_url):
            yield part
        yield u'\n</head><body><div class="header">\n'
        for part in self.header(special_title):
            yield part
        yield u'\n</div><div class="content">\n'
        for part in content:
            yield part
        if not special_title or not self.title:
            yield u'\n<div class="footer">\n'
            for part in self.footer(special_title, edit_url):
                yield part
            yield u'</div>'
        yield u'</div></body></html>'


    def pages_list(self, pages, message=None, link=None, _class=None):
        """Generate the content of a page list page."""

        yield werkzeug.html.p(werkzeug.escape(message) % {'link': link})
        yield u'<ul class="%s">' % werkzeug.escape(_class or 'pagelist')
        for title in pages:
            yield werkzeug.html.li(self.wiki_link(title))
        yield u'</ul>'

    def history_list(self):
        """Generate the content of the history page."""

        _ = self.wiki._
        h = werkzeug.html
        max_rev = -1;
        title = self.title
        link = self.wiki_link(title)
        yield h.p(h(_(u'History of changes for %(link)s.')) % {'link': link})
        url = self.request.get_url(title, self.wiki.undo, method='POST')
        yield u'<form action="%s" method="POST"><ul class="history">' % url
        try:
            self.wiki._check_lock(title)
            read_only = False
        except ForbiddenErr:
            read_only = True
        for rev, date, author, comment in self.wiki.storage.page_history(title):
            if max_rev < rev:
                max_rev = rev
            if rev > 0:
                date_url = self.request.adapter.build(self.wiki.diff, {
                    'title': title, 'from_rev': rev-1, 'to_rev': rev})
            else:
                date_url = self.request.adapter.build(self.wiki.revision, {
                    'title': title, 'rev': rev})
            if read_only:
                button = u''
            else:
                button = h.input(type_="submit", name=str(rev),
                                 value=h(_(u'Undo')))
            yield h.li(h.a(self.date_html(date), href=date_url),
                       button, ' . . . . ',
                       h.i(self.wiki_link("~%s" % author, author)),
                       h.div(h(comment), class_="comment"))
        yield u'</ul>'
        yield h.input(type_="hidden", name="parent", value=max_rev)
        yield u'</form>'


    def dependencies(self):
        """Refresh the page when any of those pages was changed."""

        dependencies = set()
        for title in [self.wiki.logo_page, self.wiki.menu_page]:
            if title not in self.storage:
                dependencies.add(werkzeug.url_quote(title))
        for title in [self.wiki.menu_page]:
            if title in self.storage:
                inode, size, mtime = self.storage.page_file_meta(title)
                etag = '%s/%d-%d' % (werkzeug.url_quote(title), inode, mtime)
                dependencies.add(etag)
        return dependencies

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
        """Read the page content from storage or preview and return iterator."""

        if lines is None:
            f = self.storage.open_page(self.title)
            lines = self.storage.page_lines(f)
        return self.content_iter(lines)

    def editor_form(self, preview=None):
        """Generate the HTML for the editor."""

        _ = self.wiki._
        author = self.request.get_author()
        lines = []
        try:
            page_file = self.storage.open_page(self.title)
            lines = self.storage.page_lines(page_file)
            (rev, old_date, old_author,
                old_comment) = self.storage.page_meta(self.title)
            comment = _(u'modified')
            if old_author == author:
                comment = old_comment
        except error.NotFoundErr:
            comment = _(u'created')
            rev = -1
        except ForbiddenErr, e:
            yield werkzeug.html.p(
                werkzeug.html(_(unicode(e))))
            return
        if preview:
            lines = preview
            comment = self.request.form.get('comment', comment)
        html = werkzeug.html
        yield u'<form action="" method="POST" class="editor"><div>'
        yield u'<textarea name="text" cols="80" rows="20" id="editortext">'
        for line in lines:
            yield werkzeug.escape(line)
        yield u"""</textarea>"""
        yield html.input(type_="hidden", name="parent", value=rev)
        yield html.label(html(_(u'Comment')), html.input(name="comment",
            value=comment), class_="comment")
        yield html.label(html(_(u'Author')), html.input(name="author",
            value=self.request.get_author()), class_="comment")
        yield html.div(
                html.input(type_="submit", name="save", value=_(u'Save')),
                html.input(type_="submit", name="preview", value=_(u'Preview')),
                html.input(type_="submit", name="cancel", value=_(u'Cancel')),
                class_="buttons")
        yield u'</div></form>'
        if preview:
            yield html.h1(html(_(u'Preview, not saved')), class_="preview")
            for part in self.view_content(preview):
                yield part

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
            line_no = (new_no or old_no or 1)-1
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
            self.parser = parser.WikiWikiParser
        else:
            self.parser = parser.WikiParser
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
            except error.NotFoundErr:
                text = u''
        return self.parser.extract_links(text)

    def view_content(self, lines=None):
        if lines is None:
            f = self.storage.open_page(self.title)
            lines = self.storage.page_lines(f)
        if self.wiki.icon_page and self.wiki.icon_page in self.storage:
            icons = self.index.page_links_and_labels(self.wiki.icon_page)
            smilies = dict((emo, link) for (link, emo) in icons)
        else:
            smilies = None
        content = self.parser(lines, self.wiki_link, self.wiki_image,
                             self.highlight, self.wiki_math, smilies)
        return content

    def wiki_math(self, math):
        math_url = self.config.get('math_url',
                            'http://www.mathtran.org/cgi-bin/mathtran?tex=')
        if '%s' in math_url:
            url = math_url % werkzeug.url_quote(math)
        else:
            url = '%s%s' % (math_url, werkzeug.url_quote(math))
        label = werkzeug.escape(math, quote=True)
        return werkzeug.html.img(src=url, alt=label, class_="math")

    def dependencies(self):
        dependencies = WikiPage.dependencies(self)
        for title in [self.wiki.icon_page]:
            if title in self.storage:
                inode, size, mtime = self.storage.page_file_meta(title)
                etag = '%s/%d-%d' % (werkzeug.url_quote(title), inode, mtime)
                dependencies.add(etag)
        for link in self.index.page_links(self.title):
            if link not in self.storage:
                dependencies.add(werkzeug.url_quote(link))
        return dependencies

class WikiPageFile(WikiPage):
    """Pages of all other mime types use this for display."""

    def view_content(self, lines=None):
        if self.title not in self.storage:
            raise error.NotFoundErr()
        content = ['<p>Download <a href="%s">%s</a> as <i>%s</i>.</p>' %
                   (self.request.get_download_url(self.title),
                    werkzeug.escape(self.title), self.mime)]
        return content

    def editor_form(self, preview=None):
        _ = self.wiki._
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
        html = werkzeug.html
        yield html.p(html(
                _(u"This is a binary file, it can't be edited on a wiki. "
                  u"Please upload a new version instead.")))
        yield html.form(html.div(
            html.div(html.input(type_="file", name="data"), class_="upload"),
            html.input(type_="hidden", name="parent", value=rev),
            html.label(html(_(u'Comment')), html.input(name="comment",
                       value=comment)),
            html.label(html(_(u'Author')), html.input(name="author",
                       value=author)),
            html.div(html.input(type_="submit", name="save", value=_(u'Save')),
                     html.input(type_="submit", name="cancel",
                                value=_(u'Cancel')),
            class_="buttons")), action="", method="POST", class_="editor",
                                enctype="multipart/form-data")

class WikiPageImage(WikiPageFile):
    """Pages of mime type image/* use this for display."""

    render_file = '128x128.png'

    def view_content(self, lines=None):
        if self.title not in self.storage:
            raise error.NotFoundErr()
        content = ['<img src="%s" alt="%s">'
                   % (self.request.get_url(self.title, self.wiki.render),
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
            im.save(cache_file,'PNG')
        except IOError:
            raise UnsupportedMediaTypeErr('Image corrupted')
        cache_file.close()
        return cache_path

class WikiPageCSV(WikiPageFile):
    """Display class for type text/csv."""

    def content_iter(self, lines=None):
        import csv
        _ = self.wiki._
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
                _(u'Error parsing CSV file %{file}s on line %{line}d: %{error}s')
                % {'file': html_title, 'line': reader.line_num, 'error': e}))
        finally:
            csv_file.close()
        yield u'</table>'

    def view_content(self, lines=None):
        if self.title not in self.storage:
            raise error.NotFoundErr()
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
