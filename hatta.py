#!/usr/bin/python
# -*- coding: utf-8 -*-

# @copyright: 2008-2009 Radomir Dopieralski <hatta@sheep.art.pl>
# @license: GNU GPL, see COPYING for details.

"""
Hatta Wiki is a wiki engine designed to be used with Mercurial repositories.
It requires Mercurial and Werkzeug python modules.

Hatta's pages are just plain text files (and also images, binaries, etc.) in
some directory in your repository. For example, you can put it in your
project's "docs" directory to keep documentation. The files can be edited both
from the wiki or with a text editor -- in either case the changes committed to
the repository will appear in the recent changes and in page's history.

Usage: hatta.py [options]

Options:
  -h, --help            show this help message and exit
  -d DIR, --pages-dir=DIR
                        Store pages in DIR
  -t DIR, --cache-dir=DIR
                        Store cache in DIR
  -i INT, --interface=INT
                        Listen on interface INT
  -p PORT, --port=PORT  Listen on port PORT
  -s NAME, --script-name=NAME
                        Override SCRIPT_NAME to NAME
  -n NAME, --site-name=NAME
                        Set the name of the site to NAME
  -m PAGE, --front-page=PAGE
                        Use PAGE as the front page
  -e ENC, --encoding=ENC
                        Use encoding ENS to read and write pages
  -c FILE, --config-file=FILE
                        Read configuration from FILE
  -l LANG, --language=LANG
                        Translate interface to LANG
"""

import base64
import datetime
import difflib
import gettext
import itertools
import mimetypes
import os
import re
import tempfile
import weakref
import wsgiref.simple_server
import sqlite3

import werkzeug

# Note: we have to set these before importing mercurial
os.environ['HGENCODING'] = 'utf-8'
os.environ["HGMERGE"] = "internal:merge"
import mercurial.hg
import mercurial.ui
import mercurial.revlog
import mercurial.util

# Use word splitter for Japanese if it's available
try:
    from hatta_jp import split_japanese
except ImportError:
    split_japanese = None

__version__ = '1.2.3'

def external_link(addr):
    """Decide whether a link is absolute or internal."""

    return (addr.startswith('http://')
            or addr.startswith('https://')
            or addr.startswith('ftp://')
            or addr.startswith('mailto:'))

def page_mime(addr):
    """Guess the mime type based on the page name."""

    mime, encoding = mimetypes.guess_type(addr, strict=False)
    if encoding:
        mime = 'archive/%s' % encoding
    if mime is None:
        mime = 'text/x-wiki'
    return mime

class WikiConfig(object):
    """
    Responsible for reading and storing site configuration. Contains the
    default settings.
    """

    # Please see the bottom of the script for modifying these values.
    interface = ''
    port = 8080
    language = None
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
    white-space: -moz-pre-wrap; white-space: -pre-wrap;
    white-space: -o-pre-wrap; line-height: 1.2; color: #555753 }
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
     border-bottom: 1px solid #babdb6; clear: both }"""
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

    def __init__(self, **keywords):
        self.parse_environ()
        self.__dict__.update(keywords)

    def parse_environ(self):
        """Check the environment variables for options."""

        prefix = 'HATTA_'
        settings = {}
        for key, value in os.environ.iteritems():
            if key.startswith(prefix):
                name = key[len(prefix):].lower()
                settings[name] = value
        self.__dict__.update(settings)

    def parse_args(self):
        """Check the commandline arguments for options."""

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
        parser.add_option('-l', '--language', dest='language',
                          help='Translate interface to LANG', metavar='LANG')
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
        self.language = options.language or self.language

    def parse_files(self, files=()):
        """Check the config files for options."""

        # XXX TODO
        raise NotImplemented

class WikiStorage(object):
    """
    Provides means of storing wiki pages and keeping track of their
    change history, using Mercurial repository as the storage method.
    """

    def __init__(self, path):
        """
        Takes the path to the directory where the pages are to be kept.
        If the directory doen't exist, it will be created. If it's inside
        a Mercurial repository, that repository will be used, otherwise
        a new repository will be created in it.
        """

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
        """Go up the directory tree looking for a repository."""

        while not os.path.isdir(os.path.join(path, ".hg")):
            old_path, path = path, os.path.dirname(path)
            if path == old_path:
                return None
        return path

    def _file_path(self, title):
        return os.path.join(self.path, werkzeug.url_quote(title, safe=''))

    def _title_to_file(self, title):
        return os.path.join(self.repo_prefix,
                            werkzeug.url_quote(title, safe=''))

    def _file_to_title(self, filename):
        name = filename[len(self.repo_prefix):].strip('/')
        return werkzeug.url_unquote(name)

    def __contains__(self, title):
        return os.path.exists(self._file_path(title))

    def save_file(self, title, file_name, author=u'', comment=u'', parent=None):
        """Save an existing file as specified page."""

        user = author.encode('utf-8') or _(u'anon').encode('utf-8')
        text = comment.encode('utf-8') or _(u'comment').encode('utf-8')
        repo_file = self._title_to_file(title)
        file_path = self._file_path(title)
        lock = self._lock()
        try:
            mercurial.util.rename(file_name, file_path)
            changectx = self.repo.changectx('tip')
            tip_node = changectx.node()
            try:
                filectx_tip = changectx[repo_file]
                current_page_rev = filectx_tip.filerev()
            except mercurial.revlog.LookupError:
                self.repo.add([repo_file])
                current_page_rev = -1
            if current_page_rev != parent:
                filectx = changectx[repo_file].filectx(parent)
                parent_node = filectx.changectx().node()
                wlock = self.repo.wlock()
                try:
                    self.repo.dirstate.setparents(parent_node)
                finally:
                    del wlock
                node = self.repo.commit(files=[repo_file], text=text, user=user,
                                 force=True, empty_ok=True)
                def partial(filename):
                    return repo_file == filename
                try:
                    unresolved = mercurial.merge.update(self.repo, tip_node,
                                                        True, False, partial)
                except mercurial.util.Abort:
                    unresolved = 1, 1, 1, 1
                msg = _(u'merge of edit conflict')
                if unresolved[3]:
                    msg = _(u'forced merge of edit conflict')
                    try:
                        mercurial.merge.update(self.repo, tip_node, True, True,
                                               partial)
                    except mercurial.util.Abort:
                        msg = _(u'failed merge of edit conflict')
                user = '<wiki>'
                text = msg.encode('utf-8')
                wlock = self.repo.wlock()
                try:
                    self.repo.dirstate.setparents(tip_node, node)
                finally:
                    del wlock
            self.repo.commit(files=[repo_file], text=text, user=user,
                             force=True, empty_ok=True)
        finally:
            del lock

    def save_text(self, title, text, author=u'', comment=u'', parent=None):
        """Save text or data as specified page."""

        try:
            temp_path = tempfile.mkdtemp(dir=self.path)
            file_path = os.path.join(temp_path, 'saved')
            f = open(file_path, "wb")
            f.write(text)
            f.close()
            self.save_file(title, file_path, author, comment, parent)
        finally:
            try:
                os.unlink(file_path)
            except OSError:
                pass
            try:
                os.rmdir(temp_path)
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
        """Get page's inode number, size and last modification time."""

        try:
            (st_mode, st_ino, st_dev, st_nlink, st_uid, st_gid, st_size,
             st_atime, st_mtime, st_ctime) = os.stat(self._file_path(title))
        except OSError:
            return 0, 0, 0
        return st_ino, st_size, st_mtime

    def page_meta(self, title):
        """Get page's revision, date, last editor and his edit comment."""

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
        """Guess page's mime type ased on corresponding file name."""

        file_path = self._file_path(title)
        return page_mime(file_path)

    def _find_filectx(self, title):
        """Find the last revision in which the file existed."""

        repo_file = self._title_to_file(title)
        changectx = self.repo.changectx('tip')
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
        """Iterate over the page's history."""

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
        """Get the contents of specified revision of the page."""

        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            raise werkzeug.exceptions.NotFound()
        try:
            return filectx_tip.filectx(rev).data()
        except IndexError:
            raise werkzeug.exceptions.NotFound()

    def history(self):
        """Iterate over the history of entire wiki."""

        changectx = self.repo.changectx('tip')
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
        """Iterate over the titles of all pages in the wiki."""

        for filename in os.listdir(self.path):
            if (os.path.isfile(os.path.join(self.path, filename))
                and not filename.startswith('.')):
                yield werkzeug.url_unquote(filename)

class WikiParser(object):
    """
    Responsible for generating HTML markup from the wiki markup.

    The parser works on two levels. On the block level, it analyzes lines
    of text and decides what kind of block element they belong to (block
    elements include paragraphs, lists, headings, preformatted blocks).
    Lines belonging to the same block are joined together, and a second
    pass is made using regular expressions to parse line-level elements,
    such as links, bold and italic text and smileys.

    Some block-level elements, such as preformatted blocks, consume additional
    lines from the input until they encounter the end-of-block marker. Most
    block-level elements are just runs of marked up lines though.
    """

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
    image_pat = (ur"\{\{(?P<image_target>([^|}]|}[^|}])*)"
                 ur"(\|(?P<image_text>([^}]|}[^}])*))?}}")
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
        "code": ur"[{][{][{](?P<code_text>([^}]|[^}][}]|[^}][}][}])"
                ur"*[}]*)[}][}][}]",
        "free_link": ur"""(http|https|ftp)://\S+[^\s.,:;!?()'"/=+<>-]""",
        "italic": ur"//",
        "link": ur"\[\[(?P<link_target>([^|\]]|\][^|\]])+)"
                ur"(\|(?P<link_text>([^\]]|\][^\]])+))?\]\]",
        "image": image_pat,
        "linebreak": ur"\\\\",
        "macro": ur"[<][<](?P<macro_name>\w+)\s+"
                 ur"(?P<macro_text>([^>]|[^>][>])+)[>][>]",
        "mail": ur"""(mailto:)?\S+@\S+(\.[^\s.,:;!?()'"/=+<>-]+)+""",
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

    def _line_linebreak(self, groups):
        return u'<br>'

    def _line_smiley(self, groups):
        smiley = groups["smiley_face"]
        return self.wiki_image(self.smilies[smiley], alt=smiley,
                               class_="smiley")

    def _line_bold(self, groups):
        if 'b' in self.stack:
            return self.pop_to('b')
        else:
            self.stack.append('b')
            return u"<b>"

    def _line_italic(self, groups):
        if 'i' in self.stack:
            return self.pop_to('i')
        else:
            self.stack.append('i')
            return u"<i>"

    def _line_punct(self, groups):
        text = groups["punct"]
        return self.punct.get(text, text)

    def _line_newline(self, groups):
        return "\n"

    def _line_text(self, groups):
        return werkzeug.escape(groups["text"])

    def _line_math(self, groups):
        if self.wiki_math:
            return self.wiki_math(groups["math_text"])
        else:
            return "<var>%s</var>" % werkzeug.escape(groups["math_text"])

    def _line_code(self, groups):
        return u'<code>%s</code>' % werkzeug.escape(groups["code_text"])

    def _line_free_link(self, groups):
        groups['link_target'] = groups['free_link']
        return self._line_link(groups)

    def _line_mail(self, groups):
        addr = groups['mail']
        groups['link_text'] = addr
        if not addr.startswith(u'mailto:'):
            addr = u'mailto:%s' % addr
        groups['link_target'] = addr
        return self._line_link(groups)

    def _line_link(self, groups):
        target = groups['link_target']
        text = groups.get('link_text')
        if not text:
            text = target
            if '#' in text:
                text, chunk = text.split('#', 1)
        match = self.image_re.match(text)
        if match:
            image = self._line_image(match.groupdict())
            return self.wiki_link(target, text, image=image)
        return self.wiki_link(target, text)

    def _line_image(self, groups):
        target = groups['image_target']
        alt = groups.get('image_text')
        if alt is None:
            alt = target
        return self.wiki_image(target, alt)

    def _line_macro(self, groups):
        name = groups['macro_name']
        text = groups['macro_text'].strip()
        return u'<span class="%s">%s</span>' % (
            werkzeug.escape(name, quote=True),
            werkzeug.escape(text))

    def _block_code(self, block):
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

    def _block_syntax(self, block):
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
                return [u'<div class="highlight"><pre>%s</pre></div>'
                        % werkzeug.escape(inside)]

    def _block_macro(self, block):
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
            yield u'<div class="%s">%s</div>' % (
                werkzeug.escape(name, quote=True),
                werkzeug.escape(inside))

    def _block_paragraph(self, block):
        text = u"".join(block)
        yield u'<p>%s%s</p>' % (u"".join(self.parse_line(text)),
                                self.pop_to(""))

    def _block_indent(self, block):
        yield u'<pre>%s</pre>' % werkzeug.escape(u"\n".join(line.rstrip()
                                        for line in block))

    def _block_table(self, block):
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

    def _block_empty(self, block):
        yield u''

    def _block_rule(self, block):
        yield u'<hr>'

    def _block_heading(self, block):
        for line in block:
            level = min(len(self.heading_re.match(line).group(0).strip()), 5)
            self.headings[level-1] = self.headings.get(level-1, 0)+1
            label = u"-".join(str(self.headings.get(i, 0))
                              for i in range(level))
            yield u'<a name="head-%s"></a><h%d>%s</h%d>' % (
                label,
                level,
                werkzeug.escape(line.strip("= \t\n\r\v")),
                level)

    def _block_bullets(self, block):
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
        """Find all the line-level markup and return HTML for it."""

        for m in self.markup_re.finditer(line):
            func = getattr(self, "_line_%s" % m.lastgroup)
            yield func(m.groupdict())

    def parse(self, lines, wiki_link, wiki_image, wiki_syntax=None,
              wiki_math=None):
        """Parse a list of lines of wiki markup, yielding HTML for it."""

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
        self.headings = {}
        for kind, block in itertools.groupby(self.lines, key):
            func = getattr(self, "_block_%s" % kind)
            for part in func(block):
                yield part


class WikiSearch(object):
    """
    Responsible for indexing words and links, for fast searching and
    backlinks. Uses a cache directory to store the index files.
    """

    digits_pattern = re.compile(ur"""^[=+~-]?[\d,.:-]+\w?\w?%?$""", re.UNICODE)
    split_pattern = re.compile(ur"""
[A-ZĄÂÃĀÄÅÁÀĂĘÉÊĚËĒÈŚĆÇČŁÓÒÖŌÕÔŃŻŹŽÑÍÏĐÞÐÆŸØ]
[a-ząâãāäåáàăęéêěëēèśćçčłóòöōõôńżźžñíïđþðæÿø]+
|\w+""", re.X|re.UNICODE)
    word_pattern = re.compile(ur"""\w[-~&\w]+\w""", re.UNICODE)

    @property
    def con(self):
        """Lazily create a connection."""
        if not self._con:
            self._con = sqlite3.connect(self.filename)
        return self._con

    def __init__(self, cache_path, lang):
        self.path = cache_path
        self.lang = lang
        self.filename = os.path.join(cache_path, 'index.sqlite3')
        if not os.path.isdir(self.path):
            self.empty = True
            os.makedirs(self.path)
        else:
            self.empty = False
        con = sqlite3.connect(self.filename)
        con.execute('create table if not exists titles '
                         '(id integer primary key, title text);')
        con.execute('create table if not exists words '
                         '(word text, page integer, count integer);')
        con.execute('create table if not exists links '
                         '(src integer, target integer, label text, number integer);')
        con.commit()
        self._con = None

        self.stop_words_re = re.compile(u'|'.join(_(
u"""am ii iii per po re a about above
across after afterwards again against all almost alone along already also
although always am among ain amongst amoungst amount an and another any aren
anyhow anyone anything anyway anywhere are around as at back be became because
become becomes becoming been before beforehand behind being below beside
besides between beyond bill both but by can cannot cant con could couldnt
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
without would yet you your yours yourself yourselves""").split())+ur'|.*\d.*',
re.U|re.I|re.X)

    def split_text(self, text):
        for match in self.word_pattern.finditer(text):
            word = match.group(0)
            if not self.stop_words_re.match(word):
                yield word.lower()

    def split_japanese_text(self, text):
        for match in self.word_pattern.finditer(text):
            word = match.group(0)
            got_japanese = False
            for w in split_japanese(word, False):
                got_japanese = True
                yield w.lower()
            if not got_japanese:
                yield word.lower()

    def count_words(self, words):
        count = {}
        for word in words:
            count[word] = count.get(word, 0) + 1
        return count

    def get_id(self, title):
        c = self.con.execute('select id from titles where title=?;', (title,))
        idents = c.fetchone()
        if idents is not None:
            return idents[0]
        else:
            return None

    def add_id(self, title):
        self.con.execute('insert into titles (title) values (?);', (title,))

    def title_id(self, title):
        ident = self.get_id(title)
        if ident is None:
            self.add_id(title)
            ident = self.get_id(title)
        return ident

    def id_title(self, ident):
        c = self.con.execute('select title from titles where id=?;', (ident,))
        return c.fetchone()[0]

    def add_words(self, title, text):
        self.add_id(title)
        title_id = self.get_id(title)
        if self.lang == 'jp' and split_japanese:
            words = self.count_words(self.split_japanese_text(text))
        else:
            words = self.count_words(self.split_text(text))
        title_words = self.count_words(self.split_text(title))
        for word, count in title_words.iteritems():
            words[word] = words.get(word, 0) + count
        for word, count in words.iteritems():
            self.con.execute('insert into words values (?, ?, ?);',
                             (word, title_id, count))
            pass
        self.con.commit()

    def update_words(self, title, text):
        title_id = self.title_id(title)
        if self.lang == 'jp' and split_japanese:
            words = self.count_words(self.split_japanese_text(text))
        else:
            words = self.count_words(self.split_text(text))
        title_words = self.count_words(self.split_text(title))
        for word, count in title_words.iteritems():
            words[word] = words.get(word, 0) + count
        self.con.execute('delete from words where page=?;', (title_id,))
        for word, count in words.iteritems():
            self.con.execute('insert into words values (?, ?, ?);',
                             (word, title_id, count))
            pass
        self.con.commit()

    def add_links(self, title, links_and_labels):
        title_id = self.title_id(title)
        self.con.execute('delete from links where src=?;', (title_id,))
        for number, (link, label) in enumerate(links_and_labels):
            self.con.execute('insert into links values (?, ?, ?, ?);',
                             (title_id, link, label, number))
        self.con.commit()

    def page_backlinks(self, title):
        sql = 'select src from links where target=? order by number;'
        for (ident,) in self.con.execute(sql, (title,)):
            yield self.id_title(ident)

    def page_links(self, title):
        title_id = self.title_id(title)
        sql = 'select target from links where src=? order by number;'
        for (link,) in self.con.execute(sql, (title_id,)):
            yield link

    def page_links_and_labels (self, title):
        title_id = self.title_id(title)
        sql = 'select target, label from links where src=? order by number;'
        return self.con.execute(sql, (title_id,))

    def find(self, words):
        first = words[0]
        rest = words[1:]
        first_counts = self.con.execute('select page, count from words '
                                        'where word=?;', (first,))
        for title_id, count in first_counts:
            score = count
            got = True
            for word in rest:
                counts = self.con.execute('select count from words '
                                          'where word=? and page=?;',
                                          (word, title_id))
                got = False
                for c in counts:
                    score += c
                    got = True
            if got and score > 0:
                yield score, self.id_title(title_id)


class WikiResponse(werkzeug.BaseResponse, werkzeug.ETagResponseMixin,
                   werkzeug.CommonResponseDescriptorsMixin):
    """A typical HTTP response class made out of Werkzeug's mixins."""

class WikiRequest(werkzeug.BaseRequest, werkzeug.ETagRequestMixin):
    """
    A Werkzeug's request with additional functions for handling file
    uploads and wiki-specific link generation.
    """
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
        """Create HTML for a wiki link."""

        text = werkzeug.escape(label)
        if external_link(addr):
            if addr.startswith('mailto:'):
                class_ = 'external email'
                text = text.replace('@', '&#64;').replace('.', '&#46;')
                href = addr.replace('@', '%40').replace('.', '%2E')
            else:
                class_ = 'external'
                href = addr
        else:
            #addr = addr.replace('/', '%2F')
            if '#' in addr:
                addr, chunk = addr.split('#', 1)
                chunk = '#%s' % chunk
            else:
                chunk = ''
            if addr == u'':
                href = chunk
            else:
                href = self.get_page_url(addr)+chunk
            if addr in ('history', 'search'):
                class_ = 'special'
            elif addr not in self.wiki.storage:
                class_ = 'nonexistent'
        return u'<a href="%s" class="%s">%s</a>' % (href, class_, image or text)

    def wiki_image(self, addr, alt, class_='wiki'):
        """Create HTML for a wiki image."""

        chunk = ''
        if external_link(addr):
            return u'<img src="%s" class="external" alt="%s">' % (
                werkzeug.url_fix(addr), werkzeug.escape(alt))
        if '#' in addr:
            addr, chunk = addr.split('#', 1)
        if addr == '':
            return u'<a name="%s"></a>' % werkzeug.escape(chunk, quote=True)
        if addr in self.wiki.storage:
            mime = self.wiki.storage.page_mime(addr)
            if mime.startswith('image/'):
                return u'<img src="%s" class="%s" alt="%s">' % (
                    self.get_download_url(addr), class_,
                    werkzeug.escape(alt, quote="True"))
            else:
                return u'<a href="%s" class="download">%s</a>' % (
                    self.get_download_url(addr), werkzeug.escape(alt))
        else:
            return u'<a href="%s" class="nonexistent">%s</a>' % (
                self.get_page_url(addr), werkzeug.escape(alt))

    def get_author(self):
        """Try to guess the author name. Use IP address as last resort."""

        author = (self.form.get("author")
                  or werkzeug.url_unquote(self.cookies.get("author", ""))
                  or werkzeug.url_unquote(self.environ.get('REMOTE_USER', ""))
                  or self.remote_addr)
        return author

    def _get_file_stream(self):
        """Save all the POSTs to temporary files."""

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

        temp_path = tempfile.mkdtemp(dir=self.tmppath)
        file_path = os.path.join(temp_path, 'saved')
        self.tmpfiles.append(temp_path)
        # We need to wrap the file object in order to add an attribute
        tmpfile = FileWrapper(open(file_path, "wb"))
        tmpfile.tmpname = file_path
        return tmpfile

    def cleanup(self):
        """Clean up the temporary files created by POSTs."""

        for temp_path in self.tmpfiles:
            try:
                os.unlink(os.path.join(temp_path, 'saved'))
            except OSError:
                pass
            try:
                os.rmdir(temp_path)
            except OSError:
                pass

class Wiki(object):
    """
    The main class of the wiki, handling initialization of the whole
    application and most of the logic.
    """

    def __init__(self, config):
        self.dead = False
        self.config = config
        global _
        if config.language is not None:
            try:
                _ = gettext.translation('hatta', 'locale',
                                        languages=[config.language]).ugettext
            except IOError:
                _ = gettext.translation('hatta', fallback=True,
                                        languages=[config.language]).ugettext
        else:
            _ = gettext.translation('hatta', fallback=True).ugettext
        self.path = os.path.abspath(config.pages_path)
        self.cache = os.path.abspath(config.cache_path)
        self.storage = WikiStorage(self.path)
        self.parser = WikiParser()
        if not os.path.isdir(self.cache):
            os.makedirs(self.cache)
            reindex = True
        else:
            reindex = False
        self.index = WikiSearch(self.cache, self.config.language)
        if reindex:
            self.reindex(self.storage.all_pages())
        self.url_map = werkzeug.routing.Map([
            werkzeug.routing.Rule('/',
                                  defaults={'title': self.config.front_page},
                                  endpoint=self.view, methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/edit/<path:title>', endpoint=self.edit,
                                  methods=['GET']),
            werkzeug.routing.Rule('/edit/<path:title>', endpoint=self.save,
                                  methods=['POST']),
            werkzeug.routing.Rule('/history/<path:title>', endpoint=self.history,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/undo/<path:title>', endpoint=self.undo,
                                  methods=['POST']),
            werkzeug.routing.Rule('/history/', endpoint=self.recent_changes,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/history/<path:title>/<int:rev>',
                                  endpoint=self.revision, methods=['GET']),
            werkzeug.routing.Rule(
                            '/history/<title>/<int:from_rev>:<int:to_rev>',
                                  endpoint=self.diff, methods=['GET']),
            werkzeug.routing.Rule('/download/<path:title>',
                                  endpoint=self.download,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/<path:title>', endpoint=self.view,
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
            werkzeug.routing.Rule('/search/<path:title>', endpoint=self.backlinks,
                                  methods=['GET', 'POST']),
            werkzeug.routing.Rule('/off-with-his-head', endpoint=self.die,
                                  methods=['GET']),
        ])

    def html_page(self, request, title, content, page_title=u''):
        """The main page template."""

        rss = request.adapter.build(self.rss, method='GET')
        atom = request.adapter.build(self.atom, method='GET')
        icon = request.adapter.build(self.favicon, method='GET')
        yield (u'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
               '"http://www.w3.org/TR/html4/strict.dtd">')
        yield u'<html><head><title>%s - %s</title>' % (
            werkzeug.escape(page_title or title),
            werkzeug.escape(self.config.site_name))
        if self.config.style_page in self.storage:
            css = request.get_download_url(self.config.style_page)
            yield u'<link rel="stylesheet" type="text/css" href="%s">' % css
        else:
            yield (u'<style type="text/css">%s</style>'
                   % self.config.default_style)
        if page_title:
            yield u'<meta name="robots" content="NOINDEX,NOFOLLOW">'
        else:
            edit = request.adapter.build(self.edit, {'title': title})
            yield (u'<link rel="alternate" type="application/wiki" href="%s">'
                   % edit)
        yield (u'<link rel="shortcut icon" type="image/x-icon" href="%s">'
               % icon)
        yield (u'<link rel="alternate" type="application/rss+xml" '
               u'title="%s (RSS)" href="%s">' % (
                    werkzeug.escape(self.config.site_name, quote=True), rss))
        yield (u'<link rel="alternate" type="application/rss+xml" '
               u'title="%s (ATOM)" href="%s">' % (
                    werkzeug.escape(self.config.site_name, quote=True), atom))
        yield u'%s</head>' % self.config.html_head
#        if self.config.language in ('ar', 'he'):
#            yield u'<body dir="rtl">'
#        else:
        yield u'<body>'
        yield u'<div class="header">'
        if self.config.logo_page in self.storage:
            home = request.get_page_url(self.config.front_page)
            logo = request.get_download_url(self.config.logo_page)
            yield u'<a href="%s" class="logo"><img src="%s" alt="[%s]"></a>' % (
                home, logo, werkzeug.escape(self.config.front_page))
        search = request.adapter.build(self.search, method='GET')
        yield u'<form class="search" action="%s" method="GET"><div>' % search
        yield u'<input name="q" class="search">'
        yield (u'<input class="button" type="submit" value="%s">'
               % werkzeug.escape(_(u'Search'), quote=True))
        yield u'</div></form>'
        if self.config.menu_page in self.storage:
            menu = self.index.page_links_and_labels(self.config.menu_page)
            if menu:
                yield u'<div class="menu">'
                for link, label in menu:
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
            history = request.adapter.build(self.history, {'title': title},
                                            method='GET')
            backlinks = request.adapter.build(self.backlinks, {'title': title},
                                              method='GET')
            yield u'<div class="footer">'
            yield u'<a href="%s" class="edit">%s</a> ' % (edit,
                werkzeug.escape(_(u'Edit')))
            yield u'<a href="%s" class="history">%s</a> ' % (history,
                werkzeug.escape(_(u'History')))
            yield u'<a href="%s" class="history">%s</a> ' % (backlinks,
                werkzeug.escape(_(u'Backlinks')))
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
            if title not in self.storage:
                raise werkzeug.exceptions.NotFound()
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
            if title not in self.storage:
                raise werkzeug.exceptions.NotFound()
            content = ['<p>Download <a href="%s">%s</a> as <i>%s</i>.</p>'
                   % (request.get_download_url(title), werkzeug.escape(title),
                      mime)]
        return content

    def revision(self, request, title, rev):
        text = unicode(self.storage.page_revision(title, rev),
                       self.config.page_charset, 'replace')
        content = [
            u'<p>%s</p>' % (
                werkzeug.escape(
                    _(u'Content of revision %(rev)d of page %(title)s:'))
                % {'rev': rev, 'title': request.wiki_link(title, title)}
            ),
            u'<pre>%s</pre>' % werkzeug.escape(text),
        ]
        html = self.html_page(request, title, content,
            page_title=_(u'Revision of "%(title)s"') % {'title': title})
        response = self.response(request, title, html, rev=rev, etag='/old')
        return response

    def check_lock(self, title):
        if self.config.locked_page in self.storage:
            if title in self.index.page_links(self.config.locked_page):
                raise werkzeug.exceptions.Forbidden()

    def extract_links(self, text):
        links = []
        def link(addr, label=None, class_=None, image=None, alt=None):
            if external_link(addr):
                return u''
            if '#' in addr:
                addr, chunk = addr.split('#', 1)
            if addr == u'':
                return u''
            links.append((addr, label))
            return u''
        lines = text.split('\n')
        for part in self.parser.parse(lines, link, link):
            pass
        return links

    def index_text(self, title, text):
        mime = self.storage.page_mime(title)
        if mime == 'text/x-wiki':
            links = self.extract_links(text)
            self.index.add_links(title, links)
        if mime.startswith('text/'):
            self.index.update_words(title, text)
        else:
            self.index.update_words(title, u'')

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
                lines = [u'<p>%s</p>'
                         % werkzeug.escape(_(u'No preview for binaries.'))]
            return self.edit(request, title, preview=lines)
        elif request.form.get('save'):
            comment = request.form.get("comment", "")
            author = request.get_author()
            text = request.form.get("text")
            try:
                parent = int(request.form.get("parent"))
            except ValueError:
                parent = None
            if text is not None:
                if title == self.config.locked_page:
                    links, labels = self.extract_links(text)
                    if title in links:
                        raise werkzeug.exceptions.Forbidden()
                if u'href="' in comment or u'http:' in comment:
                    raise werkzeug.exceptions.Forbidden()
                if text.strip() == '':
                    self.storage.delete_page(title, author, comment)
                    url = request.get_page_url(self.config.front_page)
                else:
                    data = text.encode(self.config.page_charset)
                    self.storage.save_text(title, data, author, comment, parent)
            else:
                text = u''
                upload = request.files['data']
                f = upload.stream
                if f is not None and upload.filename is not None:
                    try:
                        self.storage.save_file(title, f.tmpname, author,
                                               comment, parent)
                    except AttributeError:
                        self.storage.save_text(title, f.read(), author,
                                               comment, parent)
                else:
                    self.storage.delete_page(title, author, comment)
                    url = request.get_page_url(self.config.front_page)
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
                    page_title=_(u'Editing "%(title)s"') % {'title': title})
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
            comment = _(u'modified')
            (rev, old_date, old_author,
                old_comment) = self.storage.page_meta(title)
            if old_author == author:
                comment = old_comment
        except werkzeug.exceptions.NotFound:
            lines = []
            comment = _(u'created')
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
        yield (u'<label class="comment">%s <input name="comment" value="%s">'
               u'</label>' % (
                    werkzeug.escape(_(u'Comment')),
                    werkzeug.escape(comment, quote=True)))
        yield u'<label>%s <input name="author" value="%s"></label>' % (
            werkzeug.escape(_(u'Author')),
            werkzeug.escape(request.get_author(), quote=True))
        yield u'<div class="buttons">'
        yield (u'<input type="submit" name="save" value="%s">'
               % werkzeug.escape(_(u'Save'), quote=True))
        yield (u'<input type="submit" name="preview" value="%s">'
               % werkzeug.escape(_(u'Preview'), quote=True))
        yield (u'<input type="submit" name="cancel" value="%s">'
               % werkzeug.escape(_(u'Cancel'), quote=True))
        yield u'</div>'
        yield u'</div></form>'
        if preview:
            yield u'<h1 id="preview">%s</h1>' % werkzeug.escape(
                _(u'Preview, not saved'))
            for part in self.view_content(request, title, preview):
                yield part

    def upload_form(self, request, title, preview=None):
        author = request.get_author()
        try:
            f = self.storage.open_page(title)
            comment = _(u'changed')
            (rev, old_date, old_author,
                old_comment) = self.storage.page_meta(title)
            if old_author == author:
                comment = old_comment
        except werkzeug.exceptions.NotFound:
            f = []
            comment = _(u'uploaded')
            rev = -1
        yield u"<p>%s</p>" % werkzeug.escape(
                _(u"This is a binary file, it can't be edited on a wiki. "
                  u"Please upload a new version instead."))
        yield (u'<form action="" method="POST" class="editor" '
               u'enctype="multipart/form-data">')
        yield u'<div><div class="upload"><input type="file" name="data"></div>'
        yield u'<input type="hidden" name="parent" value="%d">' % rev
        yield (u'<label class="comment">%s <input name="comment" value="%s">'
               u'</label>' % (
                werkzeug.escape(_(u'Comment')),
                werkzeug.escape(comment, quote=True)))
        yield u'<label>%s <input name="author" value="%s"></label>' % (
            _(u'Author'), werkzeug.escape(author))
        yield u'<div class="buttons">'
        yield (u'<input type="submit" name="save" value="%s">'
               % werkzeug.escape(_(u'Save'), quote=True))
        yield (u'<input type="submit" name="cancel" value="%s">'
               % werkzeug.escape(_(u'Cancel'), quote=True))
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
            item = (u'<item><title>%s</title><link>%s</link>'
                    u'<description>%s</description><pubDate>%s</pubDate>'
                    u'<dc:creator>%s</dc:creator><guid>%s</guid></item>' % (
                werkzeug.escape(title),
                request.adapter.build(self.view, {'title': title},
                                                  force_external=True),
                werkzeug.escape(comment),
                date.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                werkzeug.escape(author),
                request.adapter.build(self.revision,
                                      {'title': title, 'rev': rev})
            ))
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
    <description>%s</description>
    <generator>Hatta Wiki</generator>
    <language>en</language>
    <lastBuildDate>%s</lastBuildDate>

""" % (
            werkzeug.escape(self.config.site_name),
            request.adapter.build(self.rss),
            request.adapter.build(self.recent_changes),
            werkzeug.escape(_(u'Track the most recent changes to the wiki '
                              u'in this feed.')),
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
            response.set_etag(u'%s/%s/%s' % (etag, werkzeug.url_quote(title),
                                             rev))
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
                comment = _(u'Delete page %(title)s') % {'title': title}
                data = ''
                self.storage.delete_page(title, author, comment)
            else:
                comment = _(u'Undo of change %(rev)d of page %(title)s') % {
                    'rev': rev, 'title': title}
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
                                 page_title=_(u'History of "%(title)s"') % {
                                    'title': title})
        response = self.response(request, title, content, '/history')
        return response

    def history_list(self, request, title):
        yield u'<p>%s</p>' % (
            _(u'History of changes for %(link)s.') % {
                'link': request.wiki_link(title, title)})
        url = request.adapter.build(self.undo, {'title': title}, method='POST')
        yield u'<form action="%s" method="POST"><ul class="history">' % url
        for rev, date, author, comment in self.storage.page_history(title):
            if rev > 0:
                url = request.adapter.build(self.diff, {
                    'title': title, 'from_rev': rev-1, 'to_rev': rev})
            else:
                url = request.adapter.build(self.revision, {
                    'title': title, 'rev': rev})
            yield u'<li>'
            yield werkzeug.html.a(date.strftime('%F %H:%M'), href=url)
            yield (u'<input type="submit" name="%d" value="Undo" '
                   u'class="button">' % rev)
            yield u' . . . . '
            yield request.wiki_link(author, author)
            yield u'<div class="comment">%s</div>' % werkzeug.escape(comment)
            yield u'</li>'
        yield u'</ul></form>'

    def recent_changes(self, request):
        content = self.html_page(request, u'history',
                                 self.changes_list(request),
                                 page_title=_(u'Recent changes'))
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
            [u'<p>%s</p>' % werkzeug.escape(_(u'Differences between revisions '
                u'%(link1)s and %(link2)s of page %(link)s.')) % {
                'link1': u'<a href="%s">%d</a>' % (from_url, from_rev),
                'link2': u'<a href="%s">%d</a>' % (to_url, to_rev),
                'link': request.wiki_link(title, title)
            }],
            self.diff_content(from_page, to_page)),
            page_title=_(u'Diff for "%(title)s"') % {'title': title})
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
        words = tuple(self.index.split_text(query))
        if not words:
            content = self.page_index(request)
            title = _(u'Page index')
        else:
            title = _(u'Searching for "%s"') % u" ".join(words)
            content = self.page_search(request, words)
        html = self.html_page(request, u'', content, page_title=title)
        return WikiResponse(html, mimetype='text/html')

    def page_index(self, request):
        yield u'<p>%s</p>' % werkzeug.escape(_(u'Index of all pages.'))
        yield u'<ul>'
        for title in sorted(self.storage.all_pages()):
            yield u'<li>%s</li>' % request.wiki_link(title, title)
        yield u'</ul>'

    def page_search(self, request, words):
        result = sorted(self.index.find(words), key=lambda x:-x[0])
        yield u'<p>%s</p>' % (
            _(u'%d page(s) containing all words:') % len(result))
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
                              page_title=_(u'Links to "%s"') % title)
        response = werkzeug.Response(html, mimetype='text/html')
        response.set_etag('/backlinks/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    def page_backlinks(self, request, title):
        yield u'<p>%s</p>' % (_(u'Pages that contain a link to %s.')
            % request.wiki_link(title, title))
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

    def reindex(self, pages):
        for title in pages:
            mime = self.storage.page_mime(title)
            if mime.startswith('text/'):
                data = self.storage.open_page(title).read()
                text = unicode(data, self.config.page_charset, 'replace')
                self.index.add_words(title, text)
                if mime == 'text/x-wiki':
                    links = self.extract_links(text)
                    self.index.add_links(title, links)
        self.index.empty = False

    def wiki_math(self, math):
        if '%s' in self.config.math_url:
            url = self.config.math_url % werkzeug.url_quote(math)
        else:
            url = ''.join([self.config.math_url, werkzeug.url_quote(math)])
        return u'<img src="%s" alt="%s" class="math">' % (url,
                                             werkzeug.escape(math, quote=True))
    def die(self, request):
        if not request.remote_addr.startswith('127.'):
            raise werkzeug.exceptions.Forbidden()
        def agony():
            yield u'Oh dear!'
            self.dead = True
        return werkzeug.Response(agony(), mimetype='text/plain')

    @werkzeug.responder
    def application(self, environ, start):
        """The main application loop."""

        if self.config.script_name is not None:
            environ['SCRIPT_NAME'] = self.config.script_name
        adapter = self.url_map.bind_to_environ(environ)
        request = WikiRequest(self, adapter, environ)
        try:
            try:
                endpoint, values = adapter.match()
                return endpoint(request, **values)
            except werkzeug.exceptions.HTTPException, err:
    #            import traceback
    #            traceback.print_exc()
                return err
        finally:
            request.cleanup()
            del request
            del adapter

def main():
    """
    Starts a standalone WSGI server.
    """

    config = WikiConfig(
        # Here you can modify the configuration: uncomment and change the ones
        # you need. Note that it's better use environment variables or command
        # line switches.

        # interface='',
        # port=8080,
        # pages_path = 'docs',
        # cache_path = 'cache',
        # front_page = 'Home',
        # site_name = 'Hatta Wiki',
        # page_charset = 'UTF-8',
    )
    config.parse_args()
    host, port = config.interface, int(config.port)
    wiki = Wiki(config)
    server = wsgiref.simple_server.make_server(host, port, wiki.application)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
