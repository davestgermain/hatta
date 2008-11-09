#!/usr/bin/python
# -*- coding: utf-8 -*-

import datetime
import itertools
import imghdr
import mimetypes
import os
import re
import tempfile
import weakref

import werkzeug

class WikiStorage(object):
    def __init__(self, path):
        os.environ['HGENCODING'] = 'utf-8'
        os.environ["HGMERGE"] = "internal:fail"
        import mercurial.hg
        import mercurial.ui

        self.path = path
        self._lockref = None
        if not os.path.exists(self.path):
            os.makedirs(self.path)
        self.repo_path = self._find_repo_path(self.path)
        self.ui = mercurial.ui.ui(report_untrusted=False, interactive=False,
                                  quiet=True)
        if self.repo_path is None:
            self.repo_path = self.path
            self.repo = mercurial.hg.repository(self.ui, self.repo_path,
                                                create=True)
        else:
            self.repo = mercurial.hg.repository(self.ui, self.repo_path)
        self.repo_prefix = self.path[len(self.repo_path):].strip('/')

    def _lock(self):
        if self._lockref and self._lockref():
            return self._lockref()
        lock = self.repo._lock(os.path.join(self.path, "wikilock"),
                               True, None, None, "Main wiki lock")
        self._lockref = weakref.ref(lock)
        return lock

    def _find_repo_path(self, path):
        while not os.path.isdir(os.path.join(path, ".hg")):
            old_path, path = path, os.path.dirname(path)
            if path == old_path:
                return None
        return path

    def _file_path(self, title):
        return os.path.join(self.path, werkzeug.url_quote(title, safe=''))

    def _title_to_file(self, title):
        return os.path.join(self.repo_prefix, werkzeug.url_quote(title, safe=''))
    def _file_to_title(self, filename):
        name = filename[len(self.repo_prefix):].strip('/')
        return werkzeug.url_unquote(name)

    def __contains__(self, title):
        return os.path.exists(self._file_path(title))

    def save_file(self, title, file_name, author=u'', comment=u''):
        user = author.encode('utf-8') or 'anon'
        text = comment.encode('utf-8') or 'comment'
        repo_file = self._title_to_file(title)
        file_path = self._file_path(title)
        lock = self._lock()
        try:
            os.rename(file_name, file_path)
            if repo_file not in self.repo.changectx():
                self.repo.add([repo_file])
            self.repo.commit(files=[repo_file], text=text, user=user,
                             force=True)
        finally:
            del lock

    def save_text(self, title, text, author=u'', comment=u''):
        try:
            tmpfd, file_name = tempfile.mkstemp(dir=self.path)
            f = os.fdopen(tmpfd, "w+b")
            f.write(text)
            f.close()
            self.save_file(title, file_name, author, comment)
        finally:
            try:
                os.unlink(file_name)
            except OSError:
                pass

    def open_page(self, title):
        try:
            return open(self._file_path(title), "rb")
        except IOError:
            raise werkzeug.exceptions.NotFound()

    def page_date(self, title):
        stamp = os.path.getmtime(self._file_path(title))
        return datetime.datetime.fromtimestamp(stamp)

    def page_mime(self, title):
        file_path = self._file_path(title)
        mime, encoding = mimetypes.guess_type(file_path, strict=False)
        if encoding:
            mime = 'archive/%s' % encoding
        if mime is None and title in self:
            sample = self.open_page(title).read(8)
            image = imghdr.what(file_path, sample)
            if image is not None:
                mime = 'image/%s' % image
        if mime is None:
            mime = 'text/x-wiki'
        return mime

class WikiParser(object):
    bullets_pat = ur"^\s*[*]+\s+"
    bullets_re = re.compile(bullets_pat, re.U)
    heading_pat = ur"^\s*=+"
    heading_re = re.compile(heading_pat, re.U)
    block = {
        "bullets": bullets_pat,
        "code": ur"^[{][{][{]+\s*$",
        "macro": ur"^<<\w+\s*$",
        "empty": ur"^\s*$",
        "heading": heading_pat,
        "indent": ur"^[ \t]+",
        "rule": ur"^\s*---+\s*$",
        "table": ur"^\|",
    } # note that the priority is alphabetical
    block_re = re.compile(ur"|".join("(?P<%s>%s)" % kv
                          for kv in sorted(block.iteritems())))
    code_close_re = re.compile(ur"^\}\}\}\s*$", re.U)
    macro_close_re = re.compile(ur"^>>\s*$", re.U)
    image_pat = ur"\{\{(?P<image_target>[^|}]+)(\|(?P<image_text>[^}]+))?}}"
    image_re = re.compile(image_pat, re.U)
    smilies = {
        r':)': "smile.png",
        r':(': "frown.png",
        r':P': "tongue.png",
        r':D': "grin.png",
        r';)': "wink.png",
    }
    punct = {
        r'...': "&hellip;",
        r'---': "&mdash;",
        r'--': "&ndash;",
        r'~': "&nbsp;",
        r'\~': "~",
        r'~~': "&sim;",
        r'(C)': "&copy;",
        r'-->': "&rarr;",
        r'<--': "&larr;",
        r'(R)': "&reg;",
        r'(TM)': "&trade;",
        r'%%': "&permil;",
        r'``': "&ldquo;",
        r"''": "&rdquo;",
        r",,": "&bdquo;",
    }
    markup = {
        "bold": ur"[*][*]",
        "code": ur"[{][{][{](?P<code_text>([^}]|[^}][}]|[^}][}][}])*[}]*)[}][}][}]",
        "free_link": ur"""(http|https|ftp)://\S+[^\s.,:;!?()'"/=+<>-]""",
        "italic": ur"//",
        "link": ur"\[\[(?P<link_target>[^|\]]+)(\|(?P<link_text>[^\]]+))?\]\]",
        "image": image_pat,
        "linebreak": ur"\\\\",
        "macro": ur"[<][<](?P<macro_name>\w+)\s+(?P<macro_text>([^>]|[^>][>])+)[>][>]",
        "math": ur"\$\$(?P<math_text>[^$]+)\$\$",
        "newline": ur"\n",
        "punct": ur"|".join(re.escape(k) for k in punct),
        "smiley": ur"(^|\b|(?<=\s))(?P<smiley_face>%s)((?=[\s.,:;!?)/&=+-])|$)"
                  % ur"|".join(re.escape(k) for k in smilies),
        "text": ur".+?",
    } # note that the priority is alphabetical
    markup_re = re.compile(ur"|".join("(?P<%s>%s)" % kv
                           for kv in sorted(markup.iteritems())))

    def pop_to(self, stop):
        """
            Pop from the stack until the specified tag is encoutered.
            Return string containing closing tags of everything popped.
        """
        tags = []
        tag = None
        try:
            while tag != stop:
                tag = self.stack.pop()
                tags.append(tag)
        except IndexError:
            pass
        return u"".join(u"</%s>" % tag for tag in tags)

    def line_linebreak(self, groups):
        return u'<br>'

    def line_smiley(self, groups):
        smiley = groups["smiley_face"]
        return self.wiki_image(self.smilies[smiley], alt=smiley,
                               class_="smiley")

    def line_bold(self, groups):
        if 'b' in self.stack:
            return self.pop_to('b')
        else:
            self.stack.append('b')
            return u"<b>"

    def line_italic(self, groups):
        if 'i' in self.stack:
            return self.pop_to('i')
        else:
            self.stack.append('i')
            return u"<i>"

    def line_punct(self, groups):
        text = groups["punct"]
        return self.punct.get(text, text)

    def line_newline(self, groups):
        return "\n"

    def line_text(self, groups):
        return werkzeug.escape(groups["text"])

    def line_math(self, groups):
        return "<var>%s</var>" % werkzeug.escape(groups["math_text"])

    def line_code(self, groups):
        return u'<code>%s</code>' % werkzeug.escape(groups["code_text"])

    def line_free_link(self, groups):
        groups['link_target'] = groups['free_link']
        return self.line_link(groups)

    def line_link(self, groups):
        target = groups['link_target']
        text = groups.get('link_text') or target
        match = self.image_re.match(text)
        if match:
            inside = self.line_image(match.groupdict())
        else:
            inside = werkzeug.escape(text)
        return self.wiki_link(target, inside)

    def line_image(self, groups):
        target = groups['image_target']
        alt = groups.get('image_text') or target
        return self.wiki_image(target, alt)

    def line_macro(self, groups):
        name = groups['macro_name']
        text = groups['macro_text'].strip()
        return u'<span class="%s">%s</span>' % (werkzeug.escape(name, quote=True),
            werkzeug.escape(text))

    def block_code(self, block):
        # XXX A hack to handle {{{...}}} code blocks, this method reads lines
        # directly from input.
        for part in block:
            line = self.lines.next()
            lines = []
            while not self.code_close_re.match(line):
                lines.append(line)
                line = self.lines.next()
            inside = u"\n".join(line.rstrip() for line in lines)
            yield u'<pre class="code">%s</pre>' % werkzeug.escape(inside)

    def block_macro(self, block):
        # XXX A hack to handle <<...>> macro blocks, this method reads lines
        # directly from input.
        for part in block:
            name = part.lstrip('<').strip()
            line = self.lines.next()
            lines = []
            while not self.macro_close_re.match(line):
                lines.append(line)
                line = self.lines.next()
            inside = u"\n".join(line.rstrip() for line in lines)
            yield u'<div class="%s">%s</div>' % (werkzeug.escape(name, quote=True),
                werkzeug.escape(inside))

    def block_paragraph(self, block):
        text = u"".join(block)
        yield u'<p>%s%s</p>' % (u"".join(self.parse_line(text)),
                                self.pop_to(""))

    def block_indent(self, block):
        yield u'<pre>%s</pre>' % werkzeug.escape(u"\n".join(line.rstrip()
                                        for line in block))

    def block_table(self, block):
        yield u'<table>'
        for line in block:
            yield '<tr>'
            for cell in line.strip('| \t\n\v\r').split('|'):
                yield '<td>%s</td>' % u"".join(self.parse_line(cell))
            yield '</tr>'
        yield u'</table>'

    def block_empty(self, block):
        yield u''

    def block_rule(self, block):
        yield u'<hr>'

    def block_heading(self, block):
        for line in block:
            level = min(len(self.heading_re.match(line).group(0).strip()), 5)
            yield u'<h%d>%s</h%d>' % (level,
                werkzeug.escape(line.strip("= \t\n\r\v")), level)

    def block_bullets(self, block):
        level = 0
        for line in block:
            nest = len(self.bullets_re.match(line).group(0).strip())
            if nest > level:
                yield '<ul>'
                level += 1
            elif nest < level:
                yield '</li></ul></li>'
                level -= 1
            else:
                yield '</li>'
            content = line.lstrip().lstrip('*').strip()
            yield '<li>%s%s' % (
                u"".join(self.parse_line(content)),
                self.pop_to(""))
        for i in range(level):
            yield '</li></ul>'

    def parse_line(self, line):
        for m in self.markup_re.finditer(line):
            func = getattr(self, "line_%s" % m.lastgroup)
            yield func(m.groupdict())

    def parse(self, lines, wiki_link=None, wiki_image=None):
        def key(line):
            match = self.block_re.match(line)
            if match:
                return match.lastgroup
            return "paragraph"
        self.lines = (unicode(line, "utf-8", "replace") for line in lines)
        self.stack = []
        self.wiki_link = wiki_link
        self.wiki_image = wiki_image
        for kind, block in itertools.groupby(self.lines, key):
            func = getattr(self, "block_%s" % kind)
            for part in func(block):
                yield part


class WikiRequest(werkzeug.BaseRequest, werkzeug.ETagRequestMixin):
    def __init__(self, wiki, adapter, environ, populate_request=True,
                 shallow=False):
        werkzeug.BaseRequest.__init__(self, environ, populate_request, shallow)
        self.wiki = wiki
        self.adapter = adapter
        self.tmpfiles = []
        self.tmppath = wiki.path

    def get_page_url(self, title):
        return self.adapter.build(self.wiki.view, {'title': title},
                                  method='GET')

    def get_download_url(self, title):
        return self.adapter.build(self.wiki.download, {'title': title},
                                  method='GET')

    def wiki_link(self, addr, label, class_='wiki'):
        if (addr.startswith('http://') or addr.startswith('https://')
            or addr.startswith('ftp://')):
            return u'<a href="%s" class="external">%s</a>' % (
                werkzeug.url_fix(addr), werkzeug.escape(label))
        elif addr in self.wiki.storage:
            return u'<a href="%s" class="%s">%s</a>' % (
                self.get_page_url(addr), class_, werkzeug.escape(label))
        else:
            return u'<a href="%s" class="nonexistent">%s</a>' % (
                self.get_page_url(addr), werkzeug.escape(label))

    def wiki_image(self, addr, alt, class_='wiki'):
        if (addr.startswith('http://') or addr.startswith('https://')
            or addr.startswith('ftp://')):
            return u'<img src="%s" class="external" alt="%s">' % (
                werkzeug.url_fix(addr), werkzeug.escape(alt))
        elif addr in self.wiki.storage:
            return u'<img src="%s" class="%s" alt="%s">' % (
                self.get_download_url(addr), class_, werkzeug.escape(alt))
        else:
            return u'<a href="%s" class="nonexistent">%s</a>' % (
                self.get_page_url(addr), werkzeug.escape(alt))

    def get_author(self):
        author = (self.form.get("author")
                  or werkzeug.url_unquote(self.cookies.get("author", ""))
                  or self.remote_addr)
        return author

    def _get_file_stream(self):
        class FileWrapper(file):
            def __init__(self, f):
                self.f = f

            def read(self, *args, **kw):
                return self.f.read(*args, **kw)

            def write(self, *args, **kw):
                return self.f.write(*args, **kw)

            def seek(self, *args, **kw):
                return self.f.seek(*args, **kw)

            def close(self, *args, **kw):
                return self.f.close(*args, **kw)

        tmpfd, tmpname = tempfile.mkstemp(dir=self.tmppath)
        self.tmpfiles.append(tmpname)
        # We need to wrap the file object in order to add an attribute
        tmpfile = FileWrapper(os.fdopen(tmpfd, "w+b"))
        tmpfile.tmpname = tmpname
        return tmpfile

    def cleanup(self):
        for filename in self.tmpfiles:
            try:
                os.unlink(filename)
            except OSError:
                pass

class WikiTitle(werkzeug.routing.BaseConverter):
    def to_python(self, value):
        return werkzeug.url_unquote_plus(value)

    def to_url(self, value):
        return werkzeug.url_quote_plus(value, safe='')

class WikiRedirect(werkzeug.routing.RequestRedirect):
    code = 303
    def get_response(self, environ):
        return werkzeug.redirect(self.new_url, 303)

class Wiki(object):
    front_page = 'Home'
    style_page = 'style.css'
    default_style = u"""html { background: #fff; color: #2e3436; 
font-family: sans-serif; font-size: 96% }
body { margin: 1em auto; line-height: 1.3; width: 40em }
a { color: #3465a4; text-decoration: none }
a:hover { text-decoration: underline }
a.wiki:visited { color: #204a87 }
a.nonexistent { color: #a40000; }
a.external { color: #3465a4; text-decoration: underline }
a.external:visited { color: #75507b }
a img { border: none }
img.smiley { vertical-align: middle }
div.footer { border-top: solid 1px #babdb6; text-align: right }
h1, h2, h3, h4 { color: #babdb6; font-weight: normal; letter-spacing: 0.125em}
div.buttons { text-align: center }
div.buttons input { font-weight: bold; font-size: 100%; background: #eee;
border: solid 1px #babdb6; margin: 0.25em}
.editor textarea { width: 100%; display: block; font-size: 100%; 
border: solid 1px #babdb6; }
.editor label { display:block; text-align: right }
.editor label input { font-size: 100%; border: solid 1px #babdb6; margin: 0.125em 0 }
.editor label.comment input  { width: 32em }"""

    favicon = ('\x00\x00\x01\x00\x01\x00\x10\x10\x10\x00\x01\x00\x04\x00(\x01'
'\x00\x00\x16\x00\x00\x00(\x00\x00\x00\x10\x00\x00\x00 \x00\x00\x00\x01\x00\x04'
'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
'\x00\x00\x00\x00\x00\x00=$;\x00_0T\x00oDl\x00\x80Vx\x00Nf\xa4\x00\x95m\x9a\x00'
'\xa7\x80\xa8\x00?\x83\xc5\x00\x1a\x86\xe1\x00\x98\x97\xa3\x00|\x97\xc4\x00u'
'\xb3\xd7\x00\xb4\xb7\xb5\x00R\xd2\xf5\x00\xd8\xd4\xd6\x00\x00\x00\x00\x00\xff'
'\xff!\x00\x00\x01\xff\xff\xff#fUUU\x10\xff\xf0feUS33\x0f\xf2UY\xbd\xdds3\x1f'
'\xf23m\xdd\xd8\x883\x1f\xf23\xad\xa5>\xb8A\x1f\xff\x13\xa5U>\xcc@\xff\xff\x125'
'e<\xecP\xff\xff\x116f^\xcc\x90\xff\xff\x12fU^\xee\xe0\xff\xff%UV3l\xe1\xff\xff'
'&5333!\xff\xff%32231\xff\xff"3""3!\xff\xff\xf2#331\x1f\xff\xff\xff\xf2!\x11'
'\x1f\xff\xff\xf0\x0f\x00\x00\xc0\x03\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00'
'\x80\x01\x00\x00\x80\x01\x00\x00\xc0\x03\x00\x00\xc0\x03\x00\x00\xc0\x03\x00'
'\x00\xc0\x03\x00\x00\xc0\x03\x00\x00\xc0\x03\x00\x00\xc0\x03\x00\x00\xc0\x03'
'\x00\x00\xe0\x07\x00\x00\xf8\x1f\x00\x00')

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.storage = WikiStorage(self.path)
        self.parser = WikiParser()
        self.url_map = werkzeug.routing.Map([
            werkzeug.routing.Rule('/', defaults={'title': self.front_page},
                                  endpoint=self.view,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/edit/<title:title>', endpoint=self.edit,
                                  methods=['GET', 'POST']),
            werkzeug.routing.Rule('/download/<title:title>',
                                  endpoint=self.download,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/<title:title>', endpoint=self.view,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/rss', endpoint=self.rss,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/favicon.ico', endpoint=self.favicon,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/robots.txt', endpoint=self.robots,
                                  methods=['GET']),
        ], converters={'title':WikiTitle})

    def html_page(self, request, title, content):
        rss = request.adapter.build(self.rss)
        icon = request.adapter.build(self.favicon)
        edit = request.adapter.build(self.edit, {'title': title})
        download = request.adapter.build(self.download, {'title': title})
        yield (u'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
               '"http://www.w3.org/TR/html4/strict.dtd">')
        yield u'<html><head><title>%s</title>' % werkzeug.escape(title)
        yield u'<link rel="shortcut icon" type="image/x-icon" href="%s">' % icon
        yield u'<link rel="alternate" type="application/wiki" href="%s">' % edit
        yield (u'<link rel="alternate" type="application/rss+xml" '
               u'title="Recent Changes" href="%s">' % rss)
        if self.style_page in self.storage:
            css = request.get_download_link(self.style_page)
            yield u'<link rel="stylesheet" type="text/css" href="%s">' % css
        else:
            yield u'<style type="text/css">%s</style>' % self.default_style
        yield u'</head><body><h1>%s</h1>' % werkzeug.escape(title)
        for part in content:
            yield part
        yield u'<div class="footer">'
        yield u'<a href="%s" class="edit">Edit</a> ' % edit
        yield u'<a href="%s" class="download">Download</a>' % download
        yield u'</div></body></html>'

    def view(self, request, title):
        if title not in self.storage:
            url = request.adapter.build(self.edit, {'title':title})
            raise WikiRedirect(url)
        mime = self.storage.page_mime(title)
        if mime == 'text/x-wiki':
            f = self.storage.open_page(title)
            content = self.parser.parse(f, request.wiki_link, request.wiki_image)
        elif mime.startswith('image/'):
            content = ['<img src="%s" alt="%s">'
                       % (request.get_download_url(title),
                          werkzeug.escape(title))]
        else:
            content = self.highlight(title, mime)
        html = self.html_page(request, title, content)
        response = werkzeug.Response(html, mimetype="text/html")
        date = self.storage.page_date(title)
        response.last_modified = date
        response.add_etag(u'%s/%s' % (title, date))
        response.make_conditional(request)
        return response

    def edit(self, request, title):
        if request.method == 'POST':
            if request.form.get('cancel'):
                if title in self.storage:
                    raise WikiRedirect(request.get_page_url(title))
                else:
                    raise WikiRedirect(request.get_page_url(self.front_page))
            elif request.form.get('save'):
                self.save(request, title)
        else:
            if title not in self.storage:
                status = '404 Not found'
            else:
                status = None
            if self.storage.page_mime(title).startswith('text/'):
                form = self.editor_form
            else:
                form = self.upload_form
            html = self.html_page(request, title, form(request, title))
            return werkzeug.Response(html, mimetype="text/html", status=status)
        raise werkzeug.exceptions.Forbidden()

    def highlight(self, title, mime):
        try:
            import pygments
            import pygments.util
            import pygments.lexers
            import pygments.formatters
            formatter = pygments.formatters.HtmlFormatter()
            try:
                lexer = pygments.lexers.get_lexer_for_mimetype(mime)
                css = formatter.get_style_defs('.highlight')
                f = self.storage.open_page(title)
                html = pygments.highlight(f.read(), lexer, formatter)
                f.close()
                yield u'<style type="text/css"><!--\n%s\n--></style>' % css
                yield html
                return
            except pygments.util.ClassNotFound:
                pass
        except ImportError:
            pass
        if mime.startswith('text/'):
            yield u'<pre>'
            f = self.storage.open_page(title)
            for part in f:
                yield f
            f.close()
            yield '</pre>'
        else:
            yield ('<p>Download <a href="%s">%s</a> as <i>%s</i>.</p>'
                   % (request.get_download_url(title), werkzeug.escape(title),
                      mime))

    def editor_form(self, request, title):
        yield u'<form action="" method="POST" class="editor"><div>'
        yield u'<textarea name="text" cols="80" rows="22">'
        try:
            f = self.storage.open_page(title)
        except werkzeug.exceptions.NotFound:
            f = []
        for part in f:
            yield werkzeug.escape(part)
        yield u"""</textarea>"""
        yield u'<label class="comment">Comment <input name="comment" value="%s"></label>' % werkzeug.escape('comment')
        yield u'<label>Author <input name="author" value="%s"></label>' % werkzeug.escape(request.get_author())
        yield u'<div class="buttons">'
        yield u'<input type="submit" name="save" value="Save">'
        yield u'<input type="submit" name="cancel" value="Cancel">'
        yield u'</div>'
        yield u'</div></form>'

    def upload_form(self, request, title):
        yield u"""<form action="" method="POST" enctype="multipart/form-data">
<div><input type="file" name="data"><input name="comment"
value="%(comment)s"><input name="author" value="%(author)s"><div class="buttons"
><input type="submit" name="save" value="Save"></div></div></form>""" % {
    'comment': werkzeug.escape(u'comment'),
    'author': werkzeug.escape(request.get_author()),
}

    def rss(self, request):
        return werkzeug.Response('edit', mimetype="text/plain")

    def download(self, request, title):
        headers = {
            'Cache-Control': 'max-age=60, public',
            'Vary': 'Transfer-Encoding',
            'Allow': 'GET, HEAD',
        }
        mime = self.storage.page_mime(title)
        f = self.storage.open_page(title)
        response = werkzeug.Response(f, mimetype=mime, headers=headers)
        date = self.storage.page_date(title)
        response.add_etag(u'download/%s/%s' % (title, date))
        response.last_modified = date
        response.make_conditional(request)
        return response

    def save(self, request, title):
        comment = request.form.get("comment", "")
        author = request.get_author()
        text = request.form.get("text")
        if text is not None:
            self.storage.save_text(title, text.encode('utf8'), author, comment)
            raise WikiRedirect(request.get_page_url(title))
        else:
            f = request.files['data'].stream
            if f is not None:
                try:
                    self.storage.save_file(title, f.tmpname, author, comment)
                except AttributeError:
                    self.storage.save_text(title, f.read(), author, comment)
                raise WikiRedirect(request.get_page_url(title))
        raise werkzeug.Forbidden()

    def favicon(self, request):
        return werkzeug.Response(self.favicon, mimetype='image/x-icon')


    def robots(self, request):
        robots = ('User-agent: *\r\n'
                  'Disallow: /edit/\r\n'
                  'Disallow: /rss\r\n'
                 )
        return werkzeug.Response(robots, mimetype='text/plain')

    @werkzeug.responder
    def application(self, environ, start):
        adapter = self.url_map.bind_to_environ(environ)
        request = WikiRequest(self, adapter, environ)
        try:
            endpoint, values = adapter.match()
            response = endpoint(request, **values)
        except werkzeug.exceptions.HTTPException, e:
            return e
        finally:
            request.cleanup()
        return response

application = Wiki("docs").application
if __name__ == "__main__":
    interface = ''
    port = 8080
    werkzeug.run_simple(interface, port, application, use_reloader=True,
                        extra_files=[])
