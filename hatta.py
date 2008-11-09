#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import re
import tempfile
import itertools

import werkzeug

class WikiStorage(object):
    def __init__(self, path):
        self.path = path
        if not os.path.exists(self.path):
            os.makedirs(self.path)

    def _file_path(self, title):
        return os.path.join(self.path, werkzeug.url_quote(title, safe=''))

    def __contains__(self, title):
        return os.path.exists(self._file_path(title))

    def save_file(self, title, file_name, author=u'', comment=u''):
        os.rename(file_name, self._file_path(title))

    def save_text(self, title, text, author=u'', comment=u''):
        try:
            tmpfd, file_name = tempfile.mkstemp(dir=self.path)
            f = os.fdopen(tmpfd, "w+b")
            f.write(text)
            f.close
            self.save_file(title, file_name, author, comment)
        finally:
            try:
                os.unlink(file_name)
            except OSError:
                pass

    def open_page(self, title):
        return open(self._file_path(title), "rb")

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

    def __init__(self, wiki_link=None, wiki_image=None):
        """ Create a new parser for parsing the lines of text, using
            wiki_link to generate links and wiki_image to insert images.
        """
        self.wiki_link = wiki_link
        self.wiki_image = wiki_image
        self.stack = []

    def __iter__(self):
        return self.parse()

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
                               class_="smiley", action="download")

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
        alt = groups.get('image_text')
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

    def parse(self, lines):
        def key(line):
            match = self.block_re.match(line)
            if match:
                return match.lastgroup
            return "paragraph"
        self.lines = (unicode(line, "utf-8", "replace") for line in lines)
        self.stack = []
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
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.storage = WikiStorage(self.path)
        self.parser = WikiParser()
        self.url_map = werkzeug.routing.Map([
            werkzeug.routing.Rule('/', defaults={'title': 'Home'},
                                  endpoint=self.view, methods=['GET']),
            werkzeug.routing.Rule('/edit/<title:title>', endpoint=self.edit,
                                  methods=['GET']),
            werkzeug.routing.Rule('/edit/<title:title>', endpoint=self.save,
                                  methods=['POST']),
            werkzeug.routing.Rule('/download/<title:title>',
                                  endpoint=self.download, methods=['GET']),
            werkzeug.routing.Rule('/<title:title>', endpoint=self.view,
                                  methods=['GET']),
            werkzeug.routing.Rule('/rss', endpoint=self.rss, methods=['GET']),
        ], converters={'title':WikiTitle})

    def html_page(self, request, title, content):
        style = request.get_download_url(u'style.css')
        rss = request.adapter.build(self.rss)
        yield u"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" 
"http://www.w3.org/TR/html4/strict.dtd">
<html><head><title>%(title)s</title>
<link rel="stylesheet" type="text/css" charset="utf-8" href="%(style)s">
<link rel="alternate" type="application/rss+xml" title="Recent Changes"
href="%(rss)s">
</head><body><h1>%(title)s</h1>""" % {
    'title': werkzeug.escape(title),
    'style': style,
    'rss': rss,
}
        for part in content:
            yield part
        yield u"""</body></html>"""

    def view(self, request, title):
        if title not in self.storage:
            url = request.adapter.build(self.edit, {'title':title})
            raise WikiRedirect(url)
        f = self.storage.open_page(title)
        content = self.parser.parse(f)
        html = self.html_page(request, title, content)
        return werkzeug.Response(html, mimetype="text/html")

    def edit(self, request, title):
        page_title = u"""Editing "%s"...""" % title
        html = self.html_page(request, page_title,
                              self.editor_form(request, title))
        return werkzeug.Response(html, mimetype="text/html")

    def editor_form(self, request, title):
        yield u"""<form action="" method="POST"><div><textarea
name="text" cols="80" rows="25">"""
        try:
            f = self.storage.open_page(title)
        except IOError:
            f = []
        for part in f:
            yield werkzeug.escape(part)
        yield u"""</textarea><input name="comment"
value="%(comment)s"><input name="author" value="%(author)s"><div class="buttons"
><input type="submit" name="save" value="Save"></div></div></form>""" % {
    'comment': werkzeug.escape(u'comment'),
    'author': werkzeug.escape(request.get_author()),
}

    def rss(self, request):
        return werkzeug.Response('edit', mimetype="text/plain")

    def download(self, request, title):
        return werkzeug.Response('download', mimetype="text/plain")

    def save(self, request, title):
        comment = request.form.get("comment", "")
        author = request.get_author()
        text = request.form.get("text")
        if text is not None:
            self.storage.save_text(title, text, author, comment)
            raise WikiRedirect(request.get_page_url(title))
        raise werkzeug.Forbidden()

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
