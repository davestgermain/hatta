#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Hatta Wiki is a wiki engine designed to be used with Mercurial repositories.
It requires Mercurial and Werkzeug python modules.

"""

try:
    import cPickle as pickle
except ImportError:
    import pickle
import base64
import datetime
import difflib
import itertools
import mimetypes
import os
import re
import shelve
import tempfile
import weakref

import werkzeug
os.environ['HGENCODING'] = 'utf-8'
os.environ["HGMERGE"] = "internal:merge"
import mercurial.hg
import mercurial.ui
import mercurial.revlog
import mercurial.util

try:
    from SplitJapanese import split_japanese
except ImportError:
    split_japanese = None

__version__ = '1.1.1-dev'

class WikiConfig(object):
    # Please see the bottom of the script for modifying these values.
    interface = ''
    port = 8080
    pages_path = 'docs'
    cache_path = 'cache'
    site_name = u'Hatta Wiki'
    front_page = u'Home'
    style_page = u'style.css'
    logo_page = u'logo.png'
    menu_page = u'Menu'
    locked_page = u'Locked'
    alias_page = u'Alias'
    math_url = 'http://www.mathtran.org/cgi-bin/mathtran?tex='
    script_name = None
    page_charset = 'utf-8'
    config_file = 'hatta.conf'
    html_head = u''
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
img.math, img.smiley { vertical-align: middle }
pre { font-size: 100%; white-space: pre-wrap; word-wrap: break-word; 
white-space: -moz-pre-wrap; white-space: -pre-wrap; white-space: -o-pre-wrap;
line-height: 1.2; color: #555753 }
pre.diff div.orig { font-size: 75%; color: #babdb6 }
b.highlight, pre.diff ins { font-weight: bold; background: #fcaf3e; color: #ce5c00; 
text-decoration: none }
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
hr { background: transparent; border:none; height: 0; border-bottom: 1px solid #babdb6; clear: both }"""
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

    def __init__(self, **kw):
        self._parse_environ()
        self.__dict__.update(kw)

    def _parse_environ(self):
        prefix = 'HATTA_'
        settings = {}
        for key, value in os.environ.iteritems():
            if key.startswith(prefix):
                name = key[len(prefix):].lower()
                settings[name] = value
        self.__dict__.update(settings)

    def _parse_args(self):
        import optparse
        parser = optparse.OptionParser()
        parser.add_option('-d', '--pages-dir', dest='pages_path',
                          help='Store pages in DIR', metavar='DIR')
        parser.add_option('-t', '--cache-dir', dest='cache_path',
                          help='Store cache in DIR', metavar='DIR')
        parser.add_option('-i', '--interface', dest='interface',
                          help='Listen on interface INT', metavar='INT')
        parser.add_option('-p', '--port', dest='port', type='int',
                          help='Listen on port PORT', metavar='PORT')
        parser.add_option('-s', '--script-name', dest='script_name',
                          help='Override SCRIPT_NAME to NAME', metavar='NAME')
        parser.add_option('-n', '--site-name', dest='site_name',
                          help='Set the name of the site to NAME',
                          metavar='NAME')
        parser.add_option('-m', '--front-page', dest='front_page',
                          help='Use PAGE as the front page', metavar='PAGE')
        parser.add_option('-e', '--encoding', dest='page_charset',
                          help='Use encoding ENS to read and write pages',
                          metavar='ENC')
        parser.add_option('-c', '--config-file', dest='config_file',
                          help='Read configuration from FILE', metavar='FILE')
        options, args = parser.parse_args()
        self.pages_path = options.pages_path or self.pages_path
        self.cache_path = options.cache_path or self.cache_path
        self.interface = options.interface or self.interface
        self.port = options.port or self.port
        self.script_name = options.script_name or self.script_name
        self.site_name = options.site_name or self.site_name
        self.page_charset = options.page_charset or self.page_charset
        self.front_page = options.front_page or self.front_page
        self.config_file = options.config_file or self.config_file

    def _parse_files(self, files=()):
        import ConfigParser

def external_link(addr):
    return (addr.startswith('http://') or addr.startswith('https://')
            or addr.startswith('ftp://'))

class WikiStorage(object):
    def __init__(self, path):
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
            mercurial.util.rename(file_name, file_path)
            if repo_file not in self.repo.changectx():
                self.repo.add([repo_file])
            self.repo.commit(files=[repo_file], text=text, user=user,
                             force=True, empty_ok=True)
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

    def delete_page(self, title, author=u'', comment=u''):
        user = author.encode('utf-8') or 'anon'
        text = comment.encode('utf-8') or 'deleted'
        repo_file = self._title_to_file(title)
        file_path = self._file_path(title)
        lock = self._lock()
        try:
            try:
                os.unlink(file_path)
            except OSError:
                pass
            self.repo.remove([repo_file])
            self.repo.commit(files=[repo_file], text=text, user=user,
                             force=True, empty_ok=True)
        finally:
            del lock

    def open_page(self, title):
        try:
            return open(self._file_path(title), "rb")
        except IOError:
            raise werkzeug.exceptions.NotFound()

    def page_file_meta(self, title):
        try:
            (st_mode, st_ino, st_dev, st_nlink, st_uid, st_gid, st_size,
             st_atime, st_mtime, st_ctime) = os.stat(self._file_path(title))
        except OSError:
            return 0, 0, 0
        return st_ino, st_size, st_mtime

    def page_meta(self, title):
        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            raise werkzeug.exceptions.NotFound()
            #return -1, None, u'', u''
        rev = filectx_tip.filerev()
        filectx = filectx_tip.filectx(rev)
        date = datetime.datetime.fromtimestamp(filectx.date()[0])
        author = unicode(filectx.user(), "utf-8",
                         'replace').split('<')[0].strip()
        comment = unicode(filectx.description(), "utf-8", 'replace')
        del filectx_tip
        del filectx
        return rev, date, author, comment

    def repo_revision(self):
        return self.repo.changectx('tip').rev()

    def page_mime(self, title):
        file_path = self._file_path(title)
        mime, encoding = mimetypes.guess_type(file_path, strict=False)
        if encoding:
            mime = 'archive/%s' % encoding
        if mime is None:
            mime = 'text/x-wiki'
        return mime

    def _find_filectx(self, title):
        repo_file = self._title_to_file(title)
        changectx = self.repo.changectx()
        stack = [changectx]
        while repo_file not in changectx:
            if not stack:
                return None
            changectx = stack.pop()
            for parent in changectx.parents():
                if parent != changectx:
                    stack.append(parent)
        return changectx[repo_file]

    def page_history(self, title):
        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            return
        maxrev = filectx_tip.filerev()
        minrev = 0
        for rev in range(maxrev, minrev-1, -1):
            filectx = filectx_tip.filectx(rev)
            date = datetime.datetime.fromtimestamp(filectx.date()[0])
            author = unicode(filectx.user(), "utf-8",
                             'replace').split('<')[0].strip()
            comment = unicode(filectx.description(), "utf-8", 'replace')
            yield rev, date, author, comment

    def page_revision(self, title, rev):
        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            raise werkzeug.exceptions.NotFound()
        try:
            return filectx_tip.filectx(rev).data()
        except IndexError:
            raise werkzeug.exceptions.NotFound()

    def history(self):
        changectx = self.repo.changectx()
        maxrev = changectx.rev()
        minrev = 0
        for wiki_rev in range(maxrev, minrev-1, -1):
            change = self.repo.changectx(wiki_rev)
            date = datetime.datetime.fromtimestamp(change.date()[0])
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
        for filename in os.listdir(self.path):
            if (os.path.isfile(os.path.join(self.path, filename))
                and not filename.startswith('.')):
                yield werkzeug.url_unquote(filename)

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
        "syntax": ur"^\{\{\{\#!\w+\s*$",
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
        if self.wiki_math:
            return self.wiki_math(groups["math_text"])
        else:
            return "<var>%s</var>" % werkzeug.escape(groups["math_text"])

    def line_code(self, groups):
        return u'<code>%s</code>' % werkzeug.escape(groups["code_text"])

    def line_free_link(self, groups):
        groups['link_target'] = groups['free_link']
        return self.line_link(groups)

    def line_link(self, groups):
        target = groups['link_target']
        text = groups.get('link_text')
        if not text:
            text = target
            if '#' in text:
                text, chunk = text.split('#', 1)
        match = self.image_re.match(text)
        if match:
            image = self.line_image(match.groupdict())
            return self.wiki_link(target, text, image=image)
        return self.wiki_link(target, text)

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

    def block_syntax(self, block):
        # XXX A hack to handle {{{#!foo...}}} syntax blocks, 
        # this method reads lines
        # directly from input.
        for part in block:
            syntax = part.lstrip('{#!').strip()
            line = self.lines.next()
            lines = []
            while not self.code_close_re.match(line):
                lines.append(line)
                line = self.lines.next()
            inside = u"\n".join(line.rstrip() for line in lines)
            if self.wiki_syntax:
                return self.wiki_syntax(inside, syntax=syntax)
            else:
                return [u'<div class="highlight"><pre>%s</pre></div>' % werkzeug.escape(inside)]

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
        in_head = False
        for line in block:
            table_row = line.strip()
            is_header = table_row.startswith('|=') and table_row.endswith('=|')
            if not in_head and is_header:
                in_head = True
                yield '<thead>'
            elif in_head and not is_header:
                in_head = False
                yield '</thead>'
            yield '<tr>'
            for cell in table_row.strip('|').split('|'):
                if cell.startswith('='):
                    head = cell.strip('=')
                    yield '<th>%s</th>' % u"".join(self.parse_line(head))
                else:
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

    def parse(self, lines, wiki_link, wiki_image, wiki_syntax=None,
              wiki_math=None):
        def key(line):
            match = self.block_re.match(line)
            if match:
                return match.lastgroup
            return "paragraph"
        self.lines = iter(lines)
        self.stack = []
        self.wiki_link = wiki_link
        self.wiki_image = wiki_image
        self.wiki_syntax = wiki_syntax
        self.wiki_math = wiki_math
        for kind, block in itertools.groupby(self.lines, key):
            func = getattr(self, "block_%s" % kind)
            for part in func(block):
                yield part


class WikiSearch(object):
    stop_words_en = frozenset(u""" am ii iii per po re a about above across 
after afterwards again against all almost alone along already also although
always am among ain amongst amoungst amount an and another any aren anyhow
anyone anything anyway anywhere are around as at back be became because become
becomes becoming been before beforehand behind being below beside besides
between beyond bill both but by can cannot cant con could couldnt
describe detail do done down due during each eg eight either eleven else etc
elsewhere empty enough even ever every everyone everything everywhere except
few fifteen fifty fill find fire first five for former formerly forty found
four from front full further get give go had has hasnt have he hence her here
hereafter hereby herein hereupon hers herself him himself his how however
hundred i ie if in inc indeed interest into is it its itself keep last latter
latterly least isn less made many may me meanwhile might mill mine more
moreover most mostly move much must my myself name namely neither never
nevertheless next nine no nobody none noone nor not nothing now nowhere of off
often on once one only onto or other others otherwise our ours ourselves out
over own per perhaps please pre put rather re same see seem seemed seeming
seems serious several she should show side since sincere six sixty so some
somehow someone something sometime sometimes somewhere still such take ten than
that the their theirs them themselves then thence there thereafter thereby
therefore therein thereupon these they thick thin third this those though three
through throughout thru thus to together too toward towards twelve twenty two
un under ve until up upon us very via was wasn we well were what whatever when
whence whenever where whereafter whereas whereby wherein whereupon wherever
whether which while whither who whoever whole whom whose why will with within
without would yet you your yours yourself yourselves""".split())
    stop_words_pl = frozenset(u"""a aby acz aczkolwiek albo ale ależ aż
bardziej bardzo bez bo bowiem by byli bym być był była było były będzie będą
cali cała cały co cokolwiek coś czasami czasem czemu czwarte czy czyli dla
dlaczego dlatego do drugie drugiej dwa gdy gdyż gdzie gdziekolwiek gdzieś go i
ich ile im inna inny innych itd itp iż ja jak jakaś jakichś jakiś jakiż jako
jakoś jednak jednakże jego jej jemu jest jeszcze jeśli jeżeli już ją kiedy
kilka kimś kto ktokolwiek ktoś która które którego której który których którym
którzy lat lecz lub ma mi mimo między mnie mogą moim może możliwe można mu na
nad nam nas naszego naszych nawet nic nich nie niech nigdy nim niż no o obok od
około on ona ono oprócz oraz pan pana pani pierwsze piąte po pod podczas pomimo
ponad ponieważ powinien powinna powinni powinno poza prawie przecież przed
przede przez przy raz roku również się sobie sobą sposób swoje są ta tak taka
taki takie także tam te tego tej ten teraz też to tobie toteż trzeba trzecie
trzy tu twoim twoja twoje twym twój ty tych tylko tym u w we według wiele wielu
więc wszyscy wszystkich wszystkie wszystkim wszystko właśnie z za zapewne
zatem zawsze ze znowu znów żadna żadne żadnych że żeby""".split())
    digits_pattern = re.compile(ur"""^[=+~-]?[\d,.:-]+\w?\w?%?$""", re.UNICODE)
    split_pattern = re.compile(ur"""
[A-ZĄÂÃĀÄÅÁÀĂĘÉÊĚËĒÈŚĆÇČŁÓÒÖŌÕÔŃŻŹŽÑÍÏĐÞÐÆŸØ]
[a-ząâãāäåáàăęéêěëēèśćçčłóòöōõôńżźžñíïđþðæÿø]+
|\w+""", re.X|re.UNICODE)
    word_pattern = re.compile(ur"""[-\w.@~+:$&%#]{2,}""", re.UNICODE)

    def __init__(self, filename):
        self.filename = filename
        self.index_file = "%s.words" % self.filename
        self.links_file = "%s.links" % self.filename
        self.labels_file = "%s.labels" % self.filename
        self.backlinks_file = "%s.back" % self.filename
        self.title_file = "%s.titles" % self.filename
        self.index = shelve.open(self.index_file, protocol=2)
        self.links = shelve.open(self.links_file, protocol=2)
        self.labels = shelve.open(self.labels_file, protocol=2)
        self.backlinks = shelve.open(self.backlinks_file, protocol=2)
        try:
            f = open(self.title_file, "rb")
            self.titles = pickle.load(f)
            f.close()
        except (IOError, EOFError):
            self.titles = []

    def split_text(self, text):
        for match in self.word_pattern.finditer(text):
            word = match.group(0).strip(u"-.@~+:$&")
            if split_japanese is None:
                yield word.lower()
            else:
                japanese_words = list(split_japanese(word, False))
                if len(japanese_words) > 1:
                    for word in japanese_words:
                        yield word.lower()
                else:
                    yield word.lower()
            parts = self.split_pattern.findall(word)
            if len(parts) > 1:
                for part in parts:
                    yield part.lower()

    def filter_words(self, words):
        for word in words:
            if not 1 < len(word) < 25:
                continue
            if word in self.stop_words_en:
                continue
            if word in self.stop_words_pl:
                continue
            if self.digits_pattern.match(word):
                continue
            yield word

    def count_words(self, words):
        count = {}
        for word in words:
            count[word] = count.get(word, 0) + 1
        return count

    def get_title_id(self, title):
        try:
            ident = self.titles.index(title)
        except ValueError:
            ident = None
        if ident is not None:
            for word, counts in self.index.iteritems():
                if ident in counts:
                    del counts[ident]
        else:
            ident = len(self.titles)
            self.titles.append(title)
            f = open(self.title_file, "w+b")
            pickle.dump(self.titles, f, 2)
            f.close()
        return ident

    def add_words(self, title, text):
        ident = self.get_title_id(title)
        if text:
            words = self.count_words(self.filter_words(self.split_text(text)))
        else:
            words = {}
        title_words = self.count_words(self.filter_words(self.split_text(title)))
        for word, count in title_words.iteritems():
            words[word] = words.get(word, 0) + count
        for word, count in words.iteritems():
            encoded = word.encode("utf-8")
            if encoded not in self.index:
                stored = {}
            else:
                stored = self.index[encoded]
            stored[ident] = count
            self.index[encoded] = stored
        self.index.sync()

    def add_links(self, title, links_and_labels):
        links, labels = links_and_labels
        self.links[title.encode('utf-8', 'backslashreplace')] = links
        self.links.sync()
        self.labels[title.encode('utf-8', 'backslashreplace')] = labels
        self.labels.sync()

    def regenerate_backlinks(self):
        for key in self.backlinks:
            self.backlinks[key] = []
        for title, links in self.links.iteritems():
            ident = self.get_title_id(title)
            for link in links:
                encoded = link.encode('utf-8', 'backslashreplace')
                backlinks = self.backlinks.get(encoded, [])
                if ident not in backlinks:
                    backlinks.append(ident)
                self.backlinks[encoded] = backlinks
        self.backlinks.sync()

    def update_backlinks(self, title, old_links, new_links):
        ident = self.get_title_id(title)
        encoded_title = title.encode('utf-8', 'backslashreplace')
        for link in old_links:
            encoded = link.encode('utf-8', 'backslashreplace')
            backlinks = self.backlinks.get(encoded, [])
            try:
                backlinks.remove(ident)
            except ValueError:
                pass
            self.backlinks[encoded] = backlinks
        for link in new_links:
            encoded = link.encode('utf-8', 'backslashreplace')
            backlinks = self.backlinks.get(encoded, [])
            if ident not in backlinks:
                backlinks.append(ident)
            self.backlinks[encoded] = backlinks
        self.backlinks.sync()

    def page_backlinks(self, title):
        for ident in self.backlinks.get(title.encode('utf-8', 'backslashreplace'), []):
            yield self.titles[ident]

    def page_links(self, title):
        return self.links.get(title.encode('utf-8', 'backslashreplace'), [])

    def page_labels(self, title):
        return self.labels.get(title.encode('utf-8', 'backslashreplace'), [])

    def find(self, words):
        first = words[0]
        rest = words[1:]
        try:
            first_counts = self.index[first.encode("utf-8")]
        except KeyError:
            return
        for ident, count in first_counts.iteritems():
            score = count
            for word in rest:
                try:
                    counts = self.index[word.encode("utf-8")]
                except KeyError:
                    return
                if ident in counts:
                    score += counts[ident]
                else:
                    score = 0
            if score > 0:
                yield score, self.titles[ident]

class WikiResponse(werkzeug.BaseResponse, werkzeug.ETagResponseMixin,
                   werkzeug.CommonResponseDescriptorsMixin):
       pass

class WikiRequest(werkzeug.BaseRequest, werkzeug.ETagRequestMixin):
    charset = 'utf-8'
    encoding_errors = 'ignore'
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

    def wiki_link(self, addr, label, class_='wiki', image=None):
        if external_link(addr):
            return u'<a href="%s" class="external">%s</a>' % (
                werkzeug.url_fix(addr), image or werkzeug.escape(label))
        if '#' in addr:
            addr, chunk = addr.split('#', 1)
            chunk = '#%s' % chunk
        else:
            chunk = ''
        if addr == u'':
            return u'<a href="%s" class="%s">%s</a>' % (
                chunk, class_, image or werkzeug.escape(label))
        if addr in self.wiki.storage:
            return u'<a href="%s%s" class="%s">%s</a>' % (
                self.get_page_url(addr), chunk, class_,
                image or werkzeug.escape(label))
        elif addr in ('history', 'search'):
            return u'<a href="%s%s" class="special">%s</a>' % (
                self.get_page_url(addr), chunk, werkzeug.escape(label))
        else:
            return u'<a href="%s%s" class="nonexistent">%s</a>' % (
                self.get_page_url(addr), chunk, werkzeug.escape(label))

    def wiki_image(self, addr, alt, class_='wiki'):
        if external_link(addr):
            return u'<img src="%s" class="external" alt="%s">' % (
                werkzeug.url_fix(addr), werkzeug.escape(alt))
        if '#' in addr:
            addr, chunk = addr.split('#', 1)
        if addr in self.wiki.storage:
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

class Wiki(object):

    def __init__(self, config):
        self.config = config
        self.path = os.path.abspath(config.pages_path)
        self.cache = os.path.abspath(config.cache_path)
        self.storage = WikiStorage(self.path)
        self.parser = WikiParser()
        if not os.path.isdir(self.cache):
            os.makedirs(self.cache)
            reindex = True
        else:
            reindex = False
        self.index = WikiSearch(os.path.join(self.cache, 'index'))
        if reindex:
            self.reindex()
        self.url_map = werkzeug.routing.Map([
            werkzeug.routing.Rule('/',
                                  defaults={'title': self.config.front_page},
                                  endpoint=self.view, methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/edit/<title>', endpoint=self.edit,
                                  methods=['GET']),
            werkzeug.routing.Rule('/edit/<title>', endpoint=self.save,
                                  methods=['POST']),
            werkzeug.routing.Rule('/history/<title>', endpoint=self.history,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/undo/<title>', endpoint=self.undo,
                                  methods=['POST']),
            werkzeug.routing.Rule('/history/', endpoint=self.recent_changes,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/history/<title>/<int:rev>',
                                  endpoint=self.revision, methods=['GET']),
            werkzeug.routing.Rule('/history/<title>/<int:from_rev>:<int:to_rev>',
                                  endpoint=self.diff, methods=['GET']),
            werkzeug.routing.Rule('/download/<title>',
                                  endpoint=self.download,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/<title>', endpoint=self.view,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/feed/rss', endpoint=self.rss,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/feed/atom', endpoint=self.atom,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/favicon.ico', endpoint=self.favicon,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/robots.txt', endpoint=self.robots,
                                  methods=['GET']),
            werkzeug.routing.Rule('/search', endpoint=self.search,
                                  methods=['GET', 'POST']),
            werkzeug.routing.Rule('/search/<title>', endpoint=self.backlinks,
                                  methods=['GET', 'POST']),
        ])

    def html_page(self, request, title, content, page_title=u''):
        rss = request.adapter.build(self.rss, method='GET')
        atom = request.adapter.build(self.atom, method='GET')
        icon = request.adapter.build(self.favicon, method='GET')
        yield (u'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
               '"http://www.w3.org/TR/html4/strict.dtd">')
        yield u'<html><head><title>%s - %s</title>' % (werkzeug.escape(page_title or title), werkzeug.escape(self.config.site_name))
        if self.config.style_page in self.storage:
            css = request.get_download_url(self.config.style_page)
            yield u'<link rel="stylesheet" type="text/css" href="%s">' % css
        else:
            yield u'<style type="text/css">%s</style>' % self.config.default_style
        if page_title:
            yield u'<meta name="robots" content="NOINDEX,NOFOLLOW">'
        else:
            edit = request.adapter.build(self.edit, {'title': title})
            yield u'<link rel="alternate" type="application/wiki" href="%s">' % edit
        yield u'<link rel="shortcut icon" type="image/x-icon" href="%s">' % icon
        yield (u'<link rel="alternate" type="application/rss+xml" '
               u'title="%s (RSS)" href="%s">' % (
                    werkzeug.escape(self.config.site_name, quote=True), rss))
        yield (u'<link rel="alternate" type="application/rss+xml" '
               u'title="%s (ATOM)" href="%s">' % (
                    werkzeug.escape(self.config.site_name, quote=True), atom))
        yield u'%s</head><body><div class="header">' % self.config.html_head
        if self.config.logo_page in self.storage:
            home = request.get_page_url(self.config.front_page)
            logo = request.get_download_url(self.config.logo_page)
            yield u'<a href="%s" class="logo"><img src="%s" alt="[%s]"></a>' % (
                home, logo, werkzeug.escape(self.config.front_page))
        search = request.adapter.build(self.search, method='GET')
        yield u'<form class="search" action="%s" method="GET"><div>' % search
        yield u'<input name="q" class="search">'
        yield u'<input class="button" type="submit" value="Search">'
        yield u'</div></form>'
        if self.config.menu_page in self.storage:
            menu = self.index.page_links(self.config.menu_page)
            labels = self.index.page_labels(self.config.menu_page)
            if menu:
                yield u'<div class="menu">'
                for i, link in enumerate(menu):
                    try:
                        label = labels[i] or link
                    except IndexError:
                        pass
                    if link == title:
                        css = u' class="current"'
                    else:
                        css = u''
                    yield u'<a href="%s"%s>%s</a> ' % (
                        request.get_page_url(link), css, werkzeug.escape(label))
                yield u'</div>'
        yield u'<h1>%s</h1>' % werkzeug.escape(page_title or title)
        yield u'</div><div class="content">'
        for part in content:
            yield part
        if not page_title:
            history = request.adapter.build(self.history, {'title': title}, method='GET')
            backlinks = request.adapter.build(self.backlinks, {'title': title}, method='GET')
            yield u'<div class="footer">'
            yield u'<a href="%s" class="edit">Edit</a> ' % edit
            yield u'<a href="%s" class="history">History</a> ' % history
            yield u'<a href="%s" class="history">Backlinks</a> ' % backlinks
            yield u'</div>'
        yield u'</div></body></html>'

    def view(self, request, title):
        try:
            content = self.view_content(request, title)
            html = self.html_page(request, title, content)
            revs = []
            unique_titles = {}
            for link in itertools.chain(self.index.page_links(title),
                                        [self.config.style_page,
                                         self.config.logo_page,
                                         self.config.menu_page]):
                if link not in self.storage and link not in unique_titles:
                    unique_titles[link] = True
                    revs.append(u'%s' % werkzeug.url_quote(link))
            etag = '/(%s)' % u','.join(revs)
            response = self.response(request, title, html, etag=etag)
        except werkzeug.exceptions.NotFound:
            url = request.adapter.build(self.edit, {'title':title})
            response = werkzeug.routing.redirect(url, code=303)
        return response

    def view_content(self, request, title, lines=None):
        mime = self.storage.page_mime(title)
        if mime == 'text/x-wiki':
            if lines is None:
                f = self.storage.open_page(title)
                lines = (unicode(line, self.config.page_charset,
                     "replace") for line in f)
            content = self.parser.parse(lines, request.wiki_link,
                                        request.wiki_image, self.highlight,
                                        self.wiki_math)
        elif mime.startswith('image/'):
            content = ['<img src="%s" alt="%s">'
                       % (request.get_download_url(title),
                          werkzeug.escape(title))]
        elif mime.startswith('text/'):
            if lines is None:
                text = unicode(self.storage.open_page(title).read(),
                               self.config.page_charset, 'replace')
            else:
                text = ''.join(lines)
            content = self.highlight(text, mime=mime)
        else:
            content = ['<p>Download <a href="%s">%s</a> as <i>%s</i>.</p>'
                   % (request.get_download_url(title), werkzeug.escape(title),
                      mime)]
        return content

    def revision(self, request, title, rev):
        text = unicode(self.storage.page_revision(title, rev),
                       self.config.page_charset, 'replace')
        content = [
            u'<p>Content of revision %d of page %s:</p>'
                % (rev, request.wiki_link(title, title)),
            u'<pre>%s</pre>' % werkzeug.escape(text),
        ]
        html = self.html_page(request, title, content,
                              page_title=u'Revision of "%s"' % title)
        response = self.response(request, title, html, rev=rev, etag='/old')
        return response

    def check_lock(self, title):
        if self.config.locked_page in self.storage:
            if title in self.index.page_links(self.config.locked_page):
                raise werkzeug.exceptions.Forbidden()

    def extract_links(self, text):
        class LinkExtractor(object):
            def __init__(self):
                self.links = []
                self.link_labels = []
                self.images = []
                self.image_labels = []

            def wiki_link(self, addr, label=None, class_=None, image=None):
                if external_link(addr):
                    return u''
                if '#' in addr:
                    addr, chunk = addr.split('#', 1)
                if addr == u'':
                    return u''
                self.links.append(addr)
                self.link_labels.append(label)
                return u''

            def wiki_image(self, addr, alt=None, class_=None):
                if external_link(addr):
                    return u''
                if '#' in addr:
                    addr, chunk = addr.split('#', 1)
                if addr == u'':
                    return u''
                self.links.append(addr)
                self.link_labels.append(alt)
                return u''

        helper = LinkExtractor()
        lines = text.split('\n')
        for part in self.parser.parse(lines, helper.wiki_link,
                                      helper.wiki_image):
            pass
        return helper.links, helper.link_labels

    def index_text(self, title, text):
        mime = self.storage.page_mime(title)
        if mime == 'text/x-wiki':
            old_links = self.index.page_links(title)
            new_links, labels = self.extract_links(text)
            self.index.update_backlinks(title, old_links, new_links)
            self.index.add_links(title, (new_links, labels))
        if mime.startswith('text/'):
            self.index.add_words(title, text)
        else:
            self.index.add_words(title, u'')

    def save(self, request, title):
        self.check_lock(title)
        url = request.get_page_url(title)
        if request.form.get('cancel'):
            if title not in self.storage:
                url = request.get_page_url(self.config.front_page)
        if request.form.get('preview'):
            text = request.form.get("text")
            if text is not None:
                lines = text.split('\n')
            else:
                lines = [u'No preview for binaries.']
            return self.edit(request, title, preview=lines)
        elif request.form.get('save'):
            comment = request.form.get("comment", "")
            author = request.get_author()
            text = request.form.get("text")
            if text is not None:
                if title == self.config.locked_page:
                    links, labels = self.extract_links(text)
                    if title in links:
                        raise werkzeug.exceptions.Forbidden()
                if u'href="' in comment:
                    raise werkzeug.exceptions.Forbidden()
                if text.strip() == '':
                    self.storage.delete_page(title, author, comment)
                    url = request.get_page_url(self.config.front_page)
                else:
                    data = text.encode(self.config.page_charset)
                    self.storage.save_text(title, data, author, comment)
            else:
                f = request.files['data'].stream
                if f is not None:
                    try:
                        self.storage.save_file(title, f.tmpname, author,
                                               comment)
                    except AttributeError:
                        self.storage.save_text(title, f.read(), author,
                                               comment)
            self.index_text(title, text)
        response = werkzeug.routing.redirect(url, code=303)
        response.set_cookie('author',
                            werkzeug.url_quote(request.get_author()),
                            max_age=604800)
        return response

    def edit(self, request, title, preview=None):
        self.check_lock(title)
        if self.storage.page_mime(title).startswith('text/'):
            form = self.editor_form
        else:
            form = self.upload_form
        html = self.html_page(request, title, form(request, title, preview),
                              page_title=u'Editing "%s"' % title)
        if title not in self.storage:
            return werkzeug.Response(html, mimetype="text/html",
                                     status='404 Not found')
        elif preview:
            return werkzeug.Response(html, mimetype="text/html")
        else:
            return self.response(request, title, html, '/edit')

    def highlight(self, text, mime=None, syntax=None):
        try:
            import pygments
            import pygments.util
            import pygments.lexers
            import pygments.formatters
            import pygments.styles
            if 'tango' in pygments.styles.STYLE_MAP:
                style = 'tango'
            else:
                style = 'friendly'
            formatter = pygments.formatters.HtmlFormatter(style=style)
            try:
                if mime:
                    lexer = pygments.lexers.get_lexer_for_mimetype(mime)
                elif syntax:
                    lexer = pygments.lexers.get_lexer_by_name(syntax)
                else:
                    lexer = pygments.lexers.guess_lexer(text)
                css = formatter.get_style_defs('.highlight')
                html = pygments.highlight(text, lexer, formatter)
                yield u'<style type="text/css"><!--\n%s\n--></style>' % css
                yield html
                return
            except pygments.util.ClassNotFound:
                pass
        except ImportError:
            pass
        yield u'<pre>%s</pre>' % werkzeug.escape(text)

    def editor_form(self, request, title, preview=None):
        author = request.get_author()
        try:
            lines = self.storage.open_page(title)
            comment = 'modified'
            (rev, old_date,
             old_author, old_comment) = self.storage.page_meta(title)
            if old_author == author:
                comment = old_comment
        except werkzeug.exceptions.NotFound:
            lines = []
            comment = 'created'
            rev = -1
        if preview:
            lines = preview
            comment = request.form.get('comment', comment)
        yield u'<form action="" method="POST" class="editor"><div>'
        yield u'<textarea name="text" cols="80" rows="20">'
        for line in lines:
            yield werkzeug.escape(line)
        yield u"""</textarea>"""
        yield u'<input type="hidden" name="parent" value="%d">' % rev
        yield u'<label class="comment">Comment <input name="comment" value="%s"></label>' % werkzeug.escape(comment)
        yield u'<label>Author <input name="author" value="%s"></label>' % werkzeug.escape(request.get_author())
        yield u'<div class="buttons">'
        yield u'<input type="submit" name="save" value="Save">'
        yield u'<input type="submit" name="preview" value="Preview">'
        yield u'<input type="submit" name="cancel" value="Cancel">'
        yield u'</div>'
        yield u'</div></form>'
        if preview:
            yield u'<h1 id="preview">Preview, not saved</h1>'
            for part in self.view_content(request, title, preview):
                yield part

    def upload_form(self, request, title, preview=None):
        author = request.get_author()
        try:
            f = self.storage.open_page(title)
            comment = 'changed'
            rev, old_date, old_author, old_comment = self.storage.page_meta(title)
            if old_author == author:
                comment = old_comment
        except werkzeug.exceptions.NotFound:
            f = []
            comment = 'uploaded'
            rev = -1
        yield u"<p>This is a binary file, it can't be edited on a wiki. Please upload a new version instead.</p>"
        yield u'<form action="" method="POST" class="editor" enctype="multipart/form-data">'
        yield u'<div><div class="upload"><input type="file" name="data"></div>'
        yield u'<input type="hidden" name="parent" value="%d">' % rev
        yield u'<label class="comment">Comment <input name="comment" value="%s"></label>' % werkzeug.escape(comment)
        yield u'<label>Author <input name="author" value="%s"></label>' % werkzeug.escape(author)
        yield u'<div class="buttons">'
        yield u'<input type="submit" name="save" value="Save">'
        yield u'<input type="submit" name="cancel" value="Cancel">'
        yield u'</div></div></form>'

    def atom(self, request):
        date_format = "%Y-%m-%dT%H:%M:%SZ"
        first_date = datetime.datetime.now()
        now = first_date.strftime(date_format)
        body = []
        first_title = u''
        count = 0
        unique_titles = {}
        for title, rev, date, author, comment in self.storage.history():
            if title in unique_titles:
                continue
            unique_titles[title] = True
            count += 1
            if count > 10:
                break
            if not first_title:
                first_title = title
                first_rev = rev
                first_date = date
            item = u"""<entry>
    <title>%(title)s</title>
    <link href="%(page_url)s" />
    <content>%(comment)s</content>
    <updated>%(date)s</updated>
    <author>
        <name>%(author)s</name>
        <uri>%(author_url)s</uri>
    </author>
    <id>%(url)s</id>
</entry>""" % {
                'title': werkzeug.escape(title),
                'page_url': request.adapter.build(self.view, {'title': title},
                                                  force_external=True),
                'comment': werkzeug.escape(comment),
                'date': date.strftime(date_format),
                'author': werkzeug.escape(author),
                'author_url': request.adapter.build(self.view,
                                                    {'title': author},
                                                    force_external=True),
                'url': request.adapter.build(self.revision,
                                             {'title': title, 'rev': rev},
                                             force_external=True),
            }
            body.append(item)
        content = u"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>%(title)s</title>
  <link rel="self" href="%(atom)s"/>
  <link href="%(home)s"/>
  <id>%(home)s</id>
  <updated>%(date)s</updated>
  <logo>%(logo)s</logo>
%(body)s
</feed>""" % {
            'title': self.config.site_name,
            'home': request.adapter.build(self.view, force_external=True),
            'atom': request.adapter.build(self.atom, force_external=True),
            'date': first_date.strftime(date_format),
            'logo': request.adapter.build(self.download,
                                          {'title': self.config.logo_page},
                                          force_external=True),
            'body': u''.join(body),
        }
        response = self.response(request, 'atom', content, '/atom',
                                 'application/xml', first_rev, first_date)
        response.set_etag('/atom/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response


    def rss(self, request):
        first_date = datetime.datetime.now()
        now = first_date.strftime("%a, %d %b %Y %H:%M:%S GMT")
        rss_body = []
        first_title = u''
        count = 0
        unique_titles = {}
        for title, rev, date, author, comment in self.storage.history():
            if title in unique_titles:
                continue
            unique_titles[title] = True
            count += 1
            if count > 10:
                break
            if not first_title:
                first_title = title
                first_rev = rev
                first_date = date
            item = u'<item><title>%s</title><link>%s</link><description>%s</description><pubDate>%s</pubDate><dc:creator>%s</dc:creator><guid>%s</guid></item>' % (
                werkzeug.escape(title),
                request.get_page_url(title),
                werkzeug.escape(comment),
                date.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                werkzeug.escape(author),
                request.adapter.build(self.revision,
                                      {'title': title, 'rev': rev})
            )
            rss_body.append(item)
        rss_head = u"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"
xmlns:dc="http://purl.org/dc/elements/1.1/"
xmlns:atom="http://www.w3.org/2005/Atom"
>
<channel>
    <title>%s</title>
    <atom:link href="%s" rel="self" type="application/rss+xml" />
    <link>%s</link>
    <description>Track the most recent changes to the wiki in this feed.</description>
    <generator>Hatta Wiki</generator>
    <language>en</language>
    <lastBuildDate>%s</lastBuildDate>

""" % (
            werkzeug.escape(self.config.site_name),
            request.adapter.build(self.rss),
            request.adapter.build(self.recent_changes),
            first_date,
        )
        content = [rss_head]+rss_body+[u'</channel></rss>']
        response = self.response(request, 'rss', content, '/rss',
                                 'application/xml', first_rev, first_date)
        response.set_etag('/rss/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    def response(self, request, title, content, etag='', mime='text/html',
                 rev=None, date=None, set_size=False):
        response = WikiResponse(content, mimetype=mime)
        if rev is None:
            inode, size, mtime = self.storage.page_file_meta(title)
            response.set_etag(u'%s/%s/%d-%d' % (etag, werkzeug.url_quote(title),
                                                    inode, mtime))
            if set_size:
                response.content_length = size
        else:
            response.set_etag(u'%s/%s/%s' % (etag, werkzeug.url_quote(title), rev))
        response.make_conditional(request)
        if response.status.startswith('304'):
            response.response = []
        return response

    def download(self, request, title):
        mime = self.storage.page_mime(title)
        if mime == 'text/x-wiki':
            mime = 'text/plain'
        f = self.storage.open_page(title)
        inode, size, mtime = self.storage.page_file_meta(title)
        response = self.response(request, title, f, '/download', mime,
                                 set_size=True)
        return response

    def undo(self, request, title):
        self.check_lock(title)
        rev = None
        for key in request.form:
            try:
                rev = int(key)
            except ValueError:
                pass
        author = request.get_author()
        if rev is not None:
            if rev == 0:
                comment = u'Delete page %s' % title
                data = ''
                self.storage.delete_page(title, author, comment)
            else:
                comment = u'Undo of change %d of page %s' % (rev, title)
                data = self.storage.page_revision(title, rev-1)
                self.storage.save_text(title, data, author, comment)
            text = unicode(data, self.config.page_charset, 'replace')
            self.index_text(title, text)
        url = request.adapter.build(self.history, {'title': title},
                                    method='GET')
        return werkzeug.redirect(url, 303)

    def history(self, request, title):
        content = self.html_page(request, title,
                                 self.history_list(request, title),
                                 page_title=u'History of "%s"' % title)
        response = self.response(request, title, content, '/history')
        return response

    def history_list(self, request, title):
        yield '<p>History of changes for %s.</p>' % request.wiki_link(title, title)
        url = request.adapter.build(self.undo, {'title':title}, method='POST')
        yield u'<form action="%s" method="POST"><ul class="history">' % url
        for rev, date, author, comment in self.storage.page_history(title):
            if rev > 0:
                url = request.adapter.build(self.diff, {
                    'title': title, 'from_rev': rev-1, 'to_rev': rev})
            else:
                url = request.adapter.build(self.revision, {
                    'title': title, 'rev': rev})
            yield u'<li>'
            yield u'<a href="%s">%s</a> ' % (url, date.strftime('%F %H:%M'))
            yield u'<input type="submit" name="%d" value="Undo" class="button">' % rev
            yield u' . . . . '
            yield request.wiki_link(author, author)
            yield u'<div class="comment">%s</div>' % werkzeug.escape(comment)
            yield u'</li>'
        yield u'</ul></form>'

    def recent_changes(self, request):
        content = self.html_page(request, u'history',
                                 self.changes_list(request),
                                 page_title=u'Recent changes')
        response = werkzeug.Response(content, mimetype='text/html')
        response.set_etag('/recentchanges/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    def changes_list(self, request):
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
                url = request.adapter.build(self.diff, {
                    'title': title,
                    'from_rev': rev-1,
                    'to_rev': lastrev.get(title, rev)
                })
            elif rev == 0:
                url = request.adapter.build(self.revision, {
                    'title': title, 'rev': rev})
            else:
                url = request.adapter.build(self.history, {
                    'title': title})
            last[title] = author, comment
            lastrev[title] = rev
            yield u'<li>'
            yield u'<a href="%s">%s</a> ' % (url, date.strftime('%F %H:%M'))
            yield request.wiki_link(title, title)
            yield u' . . . . '
            yield request.wiki_link(author, author)
            yield u'<div class="comment">%s</div>' % werkzeug.escape(comment)
            yield u'</li>'
        yield u'</ul>'

    def diff(self, request, title, from_rev, to_rev):
        from_page = unicode(self.storage.page_revision(title, from_rev),
                            self.config.page_charset, 'replace')
        to_page = unicode(self.storage.page_revision(title, to_rev),
                          self.config.page_charset, 'replace')
        from_url = request.adapter.build(self.revision,
                                         {'title': title, 'rev': from_rev})
        to_url = request.adapter.build(self.revision,
                                       {'title': title, 'rev': to_rev})
        content = self.html_page(request, title, itertools.chain(
            [u'<p>Differences between revisions ',
             u'<a href="%s">%d</a>' % (from_url, from_rev),
             u' and ',
             u'<a href="%s">%d</a>' % (to_url, to_rev),
             u' of page %s.</p>' % request.wiki_link(title, title)],
            self.diff_content(from_page, to_page)),
            page_title=u'Diff for "%s"' % title)
        response = werkzeug.Response(content, mimetype='text/html')
        return response

    def diff_content(self, text, other_text):
        diff = difflib._mdiff(text.split('\n'), other_text.split('\n'))
        stack = []
        def infiniter(iterator):
            for i in iterator:
                yield i
            while True:
                yield None
        mark_re = re.compile('\0[-+^]([^\1\0]*)\1|([^\0\1])')
        yield u'<pre class="diff">'
        for old_line, new_line, changed in diff:
            old_no, old_text = old_line
            new_no, new_text = new_line
            if changed:
                yield u'<div class="change">'
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
                yield u'<div class="orig">%s</div>' % werkzeug.escape(old_text)
        yield u'</pre>'

    def search(self, request):
        query = request.values.get('q', u'')
        words = tuple(self.index.filter_words(self.index.split_text(query)))
        if not words:
            content = self.page_index(request)
            title = 'Page index'
        else:
            title = 'Searching for "%s"' % u" ".join(words)
            content = self.page_search(request, words)
        html = self.html_page(request, u'', content, page_title=title)
        return WikiResponse(html, mimetype='text/html')

    def page_index(self, request):
        yield u'<p>Index of all pages.</p>'
        yield u'<ul>'
        for title in sorted(self.storage.all_pages()):
            yield u'<li>%s</li>' % request.wiki_link(title, title)
        yield u'</ul>'

    def page_search(self, request, words):
        result = sorted(self.index.find(words), key=lambda x:-x[0])
        yield u'<p>%d page(s) containing all words:</p>' % len(result)
        yield u'<ul>'
        for score, title in result:
            yield '<li><b>%s</b> (%d)<div class="snippet">%s</div></li>' % (
                request.wiki_link(title, title),
                score,
                self.search_snippet(title, words))
        yield u'</ul>'

    def search_snippet(self, title, words):
        text = unicode(self.storage.open_page(title).read(), "utf-8", "replace")
        regexp = re.compile(u"|".join(re.escape(w) for w in words), re.U|re.I)
        match = regexp.search(text)
        if match is None:
            return u""
        position = match.start()
        min_pos = max(position - 60, 0)
        max_pos = min(position + 60, len(text))
        snippet = werkzeug.escape(text[min_pos:max_pos])
        html = regexp.sub(lambda m:u'<b class="highlight">%s</b>'
                          % werkzeug.escape(m.group(0)), snippet)
        return html

    def backlinks(self, request, title):
        content = self.page_backlinks(request, title)
        html = self.html_page(request, u'', content,
                              page_title=u'Links to "%s"' % title)
        response = self.response(request, title, html, '/backlinks')
        return response

    def page_backlinks(self, request, title):
        yield u'<p>Pages that contain a link to %s.</p>' % request.wiki_link(title, title)
        yield u'<ul>'
        for link in self.index.page_backlinks(title):
            yield '<li>%s</li>' % request.wiki_link(link, link)
        yield u'</ul>'


    def favicon(self, request):
        return werkzeug.Response(self.config.icon, mimetype='image/x-icon')

    def robots(self, request):
        robots = ('User-agent: *\r\n'
                  'Disallow: /edit\r\n'
                  'Disallow: /rss\r\n'
                  'Disallow: /history\r\n'
                  'Disallow: /search\r\n'
                 )
        return werkzeug.Response(robots, mimetype='text/plain')

    def reindex(self):
        for title in self.storage.all_pages():
            mime = self.storage.page_mime(title)
            if mime.startswith('text/'):
                data = self.storage.open_page(title).read()
                text = unicode(data, self.config.page_charset, 'replace')
            else:
                text = u''
            self.index_text(title, text)
        self.index.regenerate_backlinks()

    def wiki_math(self, math):
        if '%s' in self.config.math_url:
            url = self.config.math_url % werkzeug.url_quote(math)
        else:
            url = ''.join([self.config.math_url, werkzeug.url_quote(math)])
        return u'<img src="%s" alt="%s" class="math">' % (url,
                                             werkzeug.escape(math, quote=True))

    @werkzeug.responder
    def application(self, environ, start):
        if self.config.script_name is not None:
            environ['SCRIPT_NAME'] = self.config.script_name
        adapter = self.url_map.bind_to_environ(environ)
        request = WikiRequest(self, adapter, environ)
        try:
            try:
                endpoint, values = adapter.match()
                return endpoint(request, **values)
            except werkzeug.exceptions.HTTPException, e:
    #            import traceback
    #            traceback.print_exc()
                return e
        finally:
            request.cleanup()
            del request
            del adapter

if __name__ == "__main__":
    config = WikiConfig(
        # Here you can modify the configuration: uncomment and change the ones
        # you need. Note that it's better use environment variables or command
        # line switches.

        # interface=''
        # port=8080
        # pages_path = 'docs'
        # cache_path = 'cache'
        # front_page = 'Home'
        # site_name = 'Hatta Wiki'
        # page_charset = 'UTF-8'
    )
    config._parse_args()
    application = Wiki(config).application
    host, port = config.interface or 'localhost', int(config.port)
    werkzeug.run_simple(config.interface, port, application, use_reloader=True)
