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
  -r, --read-only       Whether the wiki should be read-only

"""

import base64
import datetime
import difflib
import gettext
import itertools
import mimetypes
import os
import re
import sqlite3
import tempfile
import thread
import weakref

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

__version__ = '1.3.1-dev'

def external_link(addr):
    """
    Decide whether a link is absolute or internal.

    >>> external_link('http://example.com')
    True
    >>> external_link('https://example.com')
    True
    >>> external_link('ftp://example.com')
    True
    >>> external_link('mailto:user@example.com')
    True
    >>> external_link('PageTitle')
    False
    >>> external_link(u'ąęśćUnicodePage')
    False

    """

    return (addr.startswith('http://')
            or addr.startswith('https://')
            or addr.startswith('ftp://')
            or addr.startswith('mailto:'))

def page_mime(addr):
    """
    Guess the mime type based on the page name.

    >>> page_mime('something.txt')
    'text/plain'
    >>> page_mime('SomePage')
    'text/x-wiki'
    >>> page_mime(u'ąęśUnicodePage')
    'text/x-wiki'
    >>> page_mime('image.png')
    'image/png'
    >>> page_mime('style.css')
    'text/css'
    >>> page_mime('archive.tar.gz')
    'archive/gzip'
    """

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

    >>> config = WikiConfig(port='2080')
    >>> config.port
    2080
    """

    # Please see the bottom of the script for modifying these values.
    interface = ''
    port = 8080
    language = None
    read_only = False
    js_editor = False
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
    config_file = None
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
blockquote { border-left:.25em solid #ccc; padding-left:.5em; margin-left:0}"""
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
        self.sanitize()

    def sanitize(self):
        """
        Convert options to their required types.

        >>> config = WikiConfig()
        >>> config.read_only = 'on'
        >>> config.port = '2080'
        >>> config.sanitize()
        >>> config.port
        2080
        >>> config.read_only
        True
        """

        if self.read_only in (True, 'True', 'true', 'TRUE',
                              '1', 'on', 'On', 'ON'):
            self.read_only = True
        else:
            self.read_only = False
        self.port = int(self.port)

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
        parser.add_option('-r', '--read-only', dest='read_only', default=False,
                          help='Whether the wiki should be read-only',
                          action="store_true")
        parser.add_option('-j', '--js-editor', dest='js_editor',
                          help='Enable JavaScript in the editor.',
                          default=False, action="store_true")
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
        self.read_only = options.read_only or self.read_only
        self.js_editor = options.js_editor or self.js_editor

    def parse_files(self, files=None):
        """Check the config files for options."""

        import ConfigParser
        if files is None:
            if self.config_file is None:
                self.config_file = 'hatta.conf'
            files = [self.config_file]
        parser = ConfigParser.SafeConfigParser()
        parser.read(files)
        settings = {}
        for section in parser.sections():
            for option, value in parser.items(section):
                settings[option] = value
        self.__dict__.update(settings)

class WikiStorage(object):
    """
    Provides means of storing wiki pages and keeping track of their
    change history, using Mercurial repository as the storage method.
    """

    def __init__(self, path, charset=None):
        """
        Takes the path to the directory where the pages are to be kept.
        If the directory doen't exist, it will be created. If it's inside
        a Mercurial repository, that repository will be used, otherwise
        a new repository will be created in it.
        """

        self.charset = 'utf-8' or None
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

    def __iter__(self):
        return self.all_pages()

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
                # Mercurial 1.1 and later need updating the merge state
                try:
                    mercurial.merge.mergestate(self.repo).mark(repo_file, "r")
                except (AttributeError, KeyError):
                    pass
            self.repo.commit(files=[repo_file], text=text, user=user,
                             force=True, empty_ok=True)
        finally:
            del lock

    def save_data(self, title, data, author=u'', comment=u'', parent=None):
        """Save data as specified page."""

        try:
            temp_path = tempfile.mkdtemp(dir=self.path)
            file_path = os.path.join(temp_path, 'saved')
            f = open(file_path, "wb")
            f.write(data)
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

    def save_text(self, title, text, author=u'', comment=u'', parent=None):
        """Save text as specified page, encoded to charset."""

        data = text.encode(self.charset)
        self.save_data(title, data, author, comment, parent)

    def page_text(self, title):
        """Read unicode text of a page."""

        data = self.open_page(title).read()
        text = unicode(data, self.charset, 'replace')
        return text

    def page_lines(self, page):
        for data in page:
            yield unicode(data, self.charset, 'replace')

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
        """Get unicode contents of specified revision of the page."""

        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            raise werkzeug.exceptions.NotFound()
        try:
            data = filectx_tip.filectx(rev).data()
        except IndexError:
            raise werkzeug.exceptions.NotFound()
        return data

    def revision_text(self, title, rev):
        data = self.page_revision(title, rev)
        text = unicode(data, self.charset, 'replace')
        return text

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

    def changed_since(self, rev):
        """Return all pages that changed since specified repository revision."""

        last = self.repo.lookup(int(rev))
        current = self.repo.lookup('tip')
        status = self.repo.status(current, last)
        modified, added, removed, deleted, unknown, ignored, clean = status
        for filename in modified+added+removed+deleted:
            return self._file_to_title(filename)

class WikiParser(object):
    r"""
    Responsible for generating HTML markup from the wiki markup.

    The parser works on two levels. On the block level, it analyzes lines
    of text and decides what kind of block element they belong to (block
    elements include paragraphs, lists, headings, preformatted blocks).
    Lines belonging to the same block are joined together, and a second
    pass is made using regular expressions to parse line-level elements,
    such as links, bold and italic text and smileys.

    Some block-level elements, such as preformatted blocks, consume additional
    lines from the input until they encounter the end-of-block marker, using
    lines_until. Most block-level elements are just runs of marked up lines
    though.

    >>> import lxml.html.usedoctest
    >>> def link(addr, label, class_=None, image=None):
    ...     href = werkzeug.escape(addr, quote=True)
    ...     text = image or werkzeug.escape(label or addr)
    ...     return u'<a href="%s">%s</a>' % (href, text)
    >>> def img(addr, label, class_=None, image=None):
    ...     href = werkzeug.escape(addr, quote=True)
    ...     text = image or werkzeug.escape(label or addr, quote=True)
    ...     return u'<img src="%s" alt="%s">' % (href, text)
    >>> def parse(text):
    ...     lines = '\n\r'.join(text.split('\n')).split('\r')
    ...     print u''.join(WikiParser(lines, link, img))

    >>> parse(u"ziew")
    <p id="line_0">ziew</p>

    >>> parse(u"d&d")
    <p id="line_0">d&amp;d</p>

    >>> parse(u"= head =")
    <a name="head-1"></a><h1 id="line_0">head</h1>

    >>> parse(u'test')
    <p id="line_0">test</p>

    >>> parse(u'test\ntest')
    <p id="line_0">test
    test</p>

    >>> parse(u'test\n\ntest')
    <p id="line_0">test</p>
    <p id="line_2">test</p>

    >>> parse(u'test\\\\test')
    <p id="line_0">test<br>test</p>

    >>> parse(u'----')
    <hr>

    >>> parse(u'==test==')
    <a name="head-0-1"></a>
    <h2 id="line_0">test</h2>

    >>> parse(u'== test')
    <a name="head-0-1"></a>
    <h2 id="line_0">test</h2>

    >>> parse(u'==test====')
    <a name="head-0-1"></a>
    <h2 id="line_0">test</h2>

    >>> parse(u'=====test')
    <a name="head-0-0-0-0-1"></a>
    <h5 id="line_0">test</h5>

    >>> parse(u'==test==\ntest\n===test===')
    <a name="head-0-1"></a>
    <h2 id="line_0">test</h2>
    <p id="line_1">test</p>
    <a name="head-0-1-1"></a>
    <h3 id="line_2">test</h3>

    >>> parse(u'test\n* test line one\n * test line two\ntest')
    <p id="line_0">test</p>
    <ul id="line_1">
        <li>test line one</li>
        <li>test line two</li>
    </ul>
    <p id="line_3">test</p>

    >>> parse(u'* test line one\n* test line two\n** Nested item')
    <ul id="line_0">
        <li>test line one</li>
        <li>test line two<ul id="line_2">
            <li>Nested item</li>
        </ul></li>
    </ul>

    >>> parse(u'test //test test// test **test test** test')
    <p id="line_0">test <i>test test</i> test <b>test test</b> test</p>

    >>> parse(u'test //test **test// test** test')
    <p id="line_0">test <i>test <b>test</b></i> test<b> test</b></p>

    >>> parse(u'**test')
    <p id="line_0"><b>test</b></p>

    >>> parse(u'|x|y|z|\n|a|b|c|\n|d|e|f|\ntest')
    <table id="line_0">
        <tr><td>x</td><td>y</td><td>z</td></tr>
        <tr><td>a</td><td>b</td><td>c</td></tr>
        <tr><td>d</td><td>e</td><td>f</td></tr>
    </table>
    <p id="line_3">test</p>

    >>> parse(u'|=x|y|=z=|\n|a|b|c|\n|d|e|=f=|')
    <table id="line_0">
        <thead><tr><th>x</th><td>y</td><th>z</th></tr></thead>
        <tr><td>a</td><td>b</td><td>c</td></tr>
        <tr><td>d</td><td>e</td><th>f</th></tr>
    </table>

    >>> parse(u'test http://example.com/test test')
    <p id="line_0">
        test <a href="http://example.com/test">
                http://example.com/test
        </a> test</p>

    >>> parse(u'http://example.com/,test, test')
    <p id="line_0">
        <a href="http://example.com/,test">http://example.com/,test</a>, test
    </p>

    >>> parse(u'(http://example.com/test)')
    <p id="line_0">
        (<a href="http://example.com/test">http://example.com/test</a>)</p>

    XXX This might be considered a bug, but impossible to detect in general.
    >>> parse(u'http://example.com/(test)')
    <p id="line_0">
        <a href="http://example.com/(test">http://example.com/(test</a>)</p>

    >>> parse(u'http://example.com/test?test&test=1')
    <p id="line_0"><a href="http://example.com/test?test&amp;test=1">
            http://example.com/test?test&amp;test=1
    </a></p>

    >>> parse(u'http://example.com/~test')
    <p id="line_0">
        <a href="http://example.com/~test">http://example.com/~test</a></p>

    >>> parse(u'[[test]] [[tset|test]]')
    <p id="line_0"><a href="test">test</a> <a href="tset">test</a></p>

    >>> parse(u'[[http://example.com|test]]')
    <p id="line_0"><a href="http://example.com">test</a></p>

    """

    bullets_pat = ur"^\s*[*]+\s+"
    bullets_re = re.compile(bullets_pat, re.U)
    heading_pat = ur"^\s*=+"
    heading_re = re.compile(heading_pat, re.U)
    quote_pat = ur"^[>]+\s+"
    quote_re = re.compile(quote_pat, re.U)
    block = {
        "bullets": bullets_pat,
        "code": ur"^[{][{][{]+\s*$",
        "conflict": ur"^<<<<<<< local\s*$",
        "empty": ur"^\s*$",
        "heading": heading_pat,
        "indent": ur"^[ \t]+",
        "macro": ur"^<<\w+\s*$",
        "quote": quote_pat,
        "rule": ur"^\s*---+\s*$",
        "syntax": ur"^\{\{\{\#!\w+\s*$",
        "table": ur"^\|",
    } # note that the priority is alphabetical
    block_re = re.compile(ur"|".join("(?P<%s>%s)" % kv
                          for kv in sorted(block.iteritems())))
    code_close_re = re.compile(ur"^\}\}\}\s*$", re.U)
    macro_close_re = re.compile(ur"^>>\s*$", re.U)
    conflict_close_re = re.compile(ur"^>>>>>>> other\s*$", re.U)
    conflict_sep_re = re.compile(ur"^=======\s*$", re.U)
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
        r'--': "&ndash;",
        r'---': "&mdash;",
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
        "free_link": ur"""(http|https|ftp)://\S+[^\s.,:;!?()'"=+<>-]""",
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
        "punct": ur'(^|\b|(?<=\s))('+ur"|".join(re.escape(k) for k in punct)+ur')((?=[\s.,:;!?)/&=+])|\b|$)',
        "smiley": ur"(^|\b|(?<=\s))(?P<smiley_face>%s)((?=[\s.,:;!?)/&=+-])|$)"
                  % ur"|".join(re.escape(k) for k in smilies),
        "text": ur".+?",
    } # note that the priority is alphabetical
    markup_re = re.compile(ur"|".join("(?P<%s>%s)" % kv
                           for kv in sorted(markup.iteritems())))


    def __init__(self, lines, wiki_link, wiki_image,
                 wiki_syntax=None, wiki_math=None):
        self.wiki_link = wiki_link
        self.wiki_image = wiki_image
        self.wiki_syntax = wiki_syntax
        self.wiki_math = wiki_math
        self.headings = {}
        self.stack = []
        # self.lines = iter(lines)
        self.line_no = 0
        self.enumerated_lines = enumerate(lines)

    def __iter__(self):
        return self.parse()

    def parse(self):
        """Parse a list of lines of wiki markup, yielding HTML for it."""

        def key(enumerated_line):
            line_no, line = enumerated_line
            match = self.block_re.match(line)
            if match:
                return match.lastgroup
            return "paragraph"

        for kind, block in itertools.groupby(self.enumerated_lines, key):
            func = getattr(self, "_block_%s" % kind)
            for part in func(block):
                yield part

    def parse_line(self, line):
        """
        Find all the line-level markup and return HTML for it.

        >>> import lxml.html.usedoctest
        >>> parser = WikiParser([], None, None)
        >>> print u''.join(parser.parse_line(u'some **bold** words'))
        some <b>bold</b> words
        >>> print u''.join(parser.parse_line(u'some **bold words'))
        some <b>bold words
        """

        for m in self.markup_re.finditer(line):
            func = getattr(self, "_line_%s" % m.lastgroup)
            yield func(m.groupdict())

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

    def lines_until(self, close_re):
        """Get lines from input until the closing markup is encountered."""

        self.line_no, line = self.enumerated_lines.next()
        while not close_re.match(line):
            yield line.rstrip()
            line_no, line = self.enumerated_lines.next()

# methods for the markup inside lines:

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

# methods for the block (multiline) markup:

    def _block_code(self, block):
        for self.line_no, part in block:
            inside = u"\n".join(self.lines_until(self.code_close_re))
            yield werkzeug.html.pre(werkzeug.html(inside), class_="code",
                                    id="line_%d" % self.line_no)

    def _block_syntax(self, block):
        for self.line_no, part in block:
            syntax = part.lstrip('{#!').strip()
            inside = u"\n".join(self.lines_until(self.code_close_re))
            if self.wiki_syntax:
                return self.wiki_syntax(inside, syntax=syntax,
                                        line_no=self.line_no)
            else:
                return [werkzeug.html.div(werkzeug.html.pre(
                    werkzeug.html(inside), id="line_%d" % self.line_no),
                    class_="highlight")]

    def _block_macro(self, block):
        for self.line_no, part in block:
            name = part.lstrip('<').strip()
            inside = u"\n".join(self.lines_until(self.macro_close_re))
            yield u'<div class="%s">%s</div>' % (
                werkzeug.escape(name, quote=True),
                werkzeug.escape(inside))

    def _block_paragraph(self, block):
        parts = []
        first_line = None
        for self.line_no, part in block:
            if first_line is None:
                first_line = self.line_no
            parts.append(part)
        text = u"".join(self.parse_line(u"".join(parts)))
        yield werkzeug.html.p(text, self.pop_to(""), id="line_%d" % first_line)

    def _block_indent(self, block):
        parts = []
        first_line = None
        for self.line_no, part in block:
            if first_line is None:
                first_line = self.line_no
            parts.append(part.rstrip())
        text = u"\n".join(parts)
        yield werkzeug.html.pre(werkzeug.html(text), id="line_%d" % first_line)

    def _block_table(self, block):
        first_line = None
        in_head = False
        for self.line_no, line in block:
            if first_line is None:
                first_line = self.line_no
                yield u'<table id="line_%d">' % first_line
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
        for self.line_no, line in block:
            yield werkzeug.html.hr()

    def _block_heading(self, block):
        for self.line_no, line in block:
            level = min(len(self.heading_re.match(line).group(0).strip()), 5)
            self.headings[level-1] = self.headings.get(level-1, 0)+1
            label = u"-".join(str(self.headings.get(i, 0))
                              for i in range(level))
            yield werkzeug.html.a(name="head-%s" % label)
            yield u'<h%d id="line_%d">%s</h%d>' % (level, self.line_no,
                werkzeug.escape(line.strip("= \t\n\r\v")), level)

    def _block_bullets(self, block):
        level = 0
        in_ul = False
        for self.line_no, line in block:
            nest = len(self.bullets_re.match(line).group(0).strip())
            while nest > level:
                if in_ul:
                    yield '<li>'
                yield '<ul id="line_%d">' % self.line_no
                in_ul = True
                level += 1
            while nest < level:
                yield '</li></ul>'
                in_ul = False
                level -= 1
            if nest == level and not in_ul:
                yield '</li>'
            content = line.lstrip().lstrip('*').strip()
            yield '<li>%s%s' % (u"".join(self.parse_line(content)),
                                self.pop_to(""))
            in_ul = False
        yield '</li></ul>'*level

    def _block_quote(self, block):
        level = 0
        in_p = False
        for self.line_no, line in block:
            nest = len(self.quote_re.match(line).group(0).strip())
            if nest == level:
                yield u'\n'
            while nest > level:
                if in_p:
                    yield '%s</p>' % self.pop_to("")
                    in_p = False
                yield '<blockquote>'
                level += 1
            while nest < level:
                if in_p:
                    yield '%s</p>' % self.pop_to("")
                    in_p = False
                yield '</blockquote>'
                level -= 1
            content = line.lstrip().lstrip('>').strip()
            if not in_p:
                yield '<p id="line_%d">' % self.line_no
                in_p = True
            yield u"".join(self.parse_line(content))
        if in_p:
            yield '%s</p>' % self.pop_to("")
        yield '</blockquote>'*level

    def _block_conflict(self, block):
        for self.line_no, part in block:
            yield u'<div class="conflict">'
            local = u"\n".join(self.lines_until(self.conflict_sep_re))
            yield werkzeug.html.pre(werkzeug.html(local),
                                    class_="local",
                                    id="line_%d" % self.line_no)
            other = u"\n".join(self.lines_until(self.conflict_close_re))
            yield werkzeug.html.pre(werkzeug.html(other),
                                    class_="other",
                                    id="line_%d" % self.line_no)
            yield u'</div>'

class WikiSearch(object):
    """
    Responsible for indexing words and links, for fast searching and
    backlinks. Uses a cache directory to store the index files.
    """

    word_pattern = re.compile(ur"""\w[-~&\w]+\w""", re.UNICODE)
    _con = {}

    def __init__(self, cache_path, lang, storage, parser):
        self.path = cache_path
        self.storage = storage
        self.parser = parser
        self.lang = lang
        if lang == "ja" and split_japanese:
            self.split_text = self.split_japanese_text
        self.filename = os.path.join(cache_path, 'index.sqlite3')
        if not os.path.isdir(self.path):
            self.empty = True
            os.makedirs(self.path)
        elif not os.path.exists(self.filename):
            self.empty = True
        else:
            self.empty = False
        con = self.con # sqlite3.connect(self.filename)
        self.con.execute('create table if not exists titles '
                '(id integer primary key, title varchar);')
        self.con.execute('create table if not exists words '
                '(word varchar, page integer, count integer);')
        self.con.execute('create table if not exists links '
                '(src integer, target integer, label varchar, number integer);')
        self.con.commit()
        self.stop_words_re = re.compile(u'^('+u'|'.join(re.escape(_(
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
without would yet you your yours yourself yourselves""")).split())
+ur')$|.*\d.*', re.U|re.I|re.X)

        changed = self.storage.changed_since(self.get_last_revision())
        self.reindex(changed)

    @property
    def con(self):
        """Keep one connection per thread."""

        thread_id = thread.get_ident()
        try:
            return self._con[thread_id]
        except KeyError:
            connection = sqlite3.connect(self.filename)
            connection.isolation_level = None
            self._con[thread_id] = connection
            return connection

    def split_text(self, text):
        """Splits text into words, removing stop words"""

        for match in self.word_pattern.finditer(text):
            word = match.group(0)
            if not self.stop_words_re.match(word):
                yield word.lower()

    def split_japanese_text(self, text):
        """Splits text into words, including rules for Japanese"""

        for match in self.word_pattern.finditer(text):
            word = match.group(0)
            got_japanese = False
            for w in split_japanese(word, False):
                got_japanese = True
                if not self.stop_words_re.match(word):
                    yield w.lower()
            if not got_japanese and not self.stop_words_re.match(word):
                yield word.lower()

    def count_words(self, words):
        count = {}
        for word in words:
            count[word] = count.get(word, 0)+1
        return count

    def title_id(self, title, con):
        c = con.execute('select id from titles where title=?;', (title,))
        idents = c.fetchone()
        if idents is None:
            con.execute('insert into titles (title) values (?);', (title,))
            c = con.execute('select last_insert_rowid();')
            idents = c.fetchone()
        return idents[0]

    def id_title(self, ident, con):
            c = con.execute('select title from titles where id=?;', (ident,))
            return c.fetchone()[0]

    def update_words(self, title, text, cursor):
        title_id = self.title_id(title, cursor)
        words = self.count_words(self.split_text(text))
        title_words = self.count_words(self.split_text(title))
        for word, count in title_words.iteritems():
            words[word] = words.get(word, 0) + count
        cursor.execute('delete from words where page=?;', (title_id,))
        for word, count in words.iteritems():
            cursor.execute('insert into words values (?, ?, ?);',
                             (word, title_id, count))

    def update_links(self, title, links_and_labels, cursor):
        title_id = self.title_id(title, cursor)
        cursor.execute('delete from links where src=?;', (title_id,))
        for number, (link, label) in enumerate(links_and_labels):
            cursor.execute('insert into links values (?, ?, ?, ?);',
                             (title_id, link, label, number))

    def page_backlinks(self, title):
        con = self.con # sqlite3.connect(self.filename)
        try:
            sql = 'select src from links where target=? order by number;'
            for (ident,) in con.execute(sql, (title,)):
                yield self.id_title(ident, con)
        finally:
            con.commit()

    def page_links(self, title):
        con = self.con # sqlite3.connect(self.filename)
        try:
            title_id = self.title_id(title, con)
            sql = 'select target from links where src=? order by number;'
            for (link,) in con.execute(sql, (title_id,)):
                yield link
        finally:
            con.commit()

    def page_links_and_labels (self, title):
        con = self.con # sqlite3.connect(self.filename)
        try:
            title_id = self.title_id(title, con)
            sql = 'select target, label from links where src=? order by number;'
            for link_and_label in con.execute(sql, (title_id,)):
                yield link_and_label
        finally:
            con.commit()

    def find(self, words):
        """Returns an iterator of all pages containing the words, and their
            scores."""

        con = self.con # sqlite3.connect(self.filename)
        try:
            first = words[0]
            rest = words[1:]
            pattern = '%%%s%%' % first
            first_counts = con.execute('select page, count from words '
                                        'where word like ?;', (pattern,))
            first_hits = {}
            for title_id, count in first_counts:
                first_hits[title_id] = first_hits.get(title_id, 0)+count

            for title_id, score in first_hits.iteritems():
                got = True
                for word in rest:
                    pattern = '%%%s%%' % word
                    counts = con.execute('select count from words '
                                         'where word like ? and page=?;',
                                         (pattern, title_id))
                    got = False
                    for count in counts:
                        score += count[0]
                        got = True
                if got and score > 0:
                    yield score, self.id_title(title_id, con)
        finally:
            con.commit()


    def reindex_page(self, title, cursor, text=None):
        """Updates the content of the database, needs locks around."""

        mime = self.storage.page_mime(title)
        if not mime.startswith('text/'):
            self.update_words(title, '', cursor=cursor)
            return
        if text is None:
            try:
                text = self.storage.page_text(title)
            except werkzeug.exceptions.NotFound:
                text = u''
        if mime == 'text/x-wiki':
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
            for part in self.parser(lines, link, link):
                pass
            self.update_links(title, links, cursor=cursor)
        self.update_words(title, text, cursor=cursor)

    def update_page(self, title, data=None, text=None):
        """Updates the index with new page content, for a single page."""

        if text is None and data is not None:
            text = unicode(data, self.storage.charset, 'replace')
        cursor = self.con.cursor()
        cursor.execute('begin immediate transaction;')
        try:
            self.set_last_revision(self.storage.repo_revision())
            self.reindex_page(title, cursor, text)
            cursor.execute('commit transaction;')
        except:
            cursor.execute('rollback;')
            raise

    def reindex(self, pages):
        """Updates specified pages in bulk."""

        cursor = self.con.cursor()
        cursor.execute('begin immediate transaction;')
        try:
            self.set_last_revision(self.storage.repo_revision())
            for title in pages:
                self.reindex_page(title, cursor)
            cursor.execute('commit transaction;')
            self.empty = False
        except:
            cursor.execute('rollback;')
            raise

    def set_last_revision(self, rev):
        # XXX we use % here because the sqlite3's substitiution doesn't work
        self.con.execute('pragma user_version=%d;' % (int(rev),))

    def get_last_revision(self):
        con = self.con
        c = con.execute('pragma user_version;')
        rev = c.fetchone()[0]
        return rev

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

    def __init__(self, wiki, adapter, environ, **kw):
        werkzeug.BaseRequest.__init__(self, environ, **kw)
        self.wiki = wiki
        self.adapter = adapter
        self.tmpfiles = []
        self.tmppath = wiki.path

    def get_url(self, title=None, view=None, method='GET',
                external=False, **kw):
        if view is None:
            view = self.wiki.view
        if title is not None:
            kw['title'] = title
        return self.adapter.build(view, kw, method=method,
                                  force_external=external)

    def get_download_url(self, title):
        return self.get_url(title, view=self.wiki.download)

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

class WikiPage(object):
    """Everything needed for rendering a page."""

    def __init__(self, wiki, request, title):
        self.wiki = wiki
        self.request = request
        self.title = title
        self.config = self.wiki.config
        self.get_url = self.request.get_url
        self.get_download_url = self.request.get_download_url

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
                href = werkzeug.escape(addr, quote=True)
        else:
            if '#' in addr:
                addr, chunk = addr.split('#', 1)
                chunk = '#%s' % chunk
            else:
                chunk = ''
            if addr == u'':
                href = chunk
            else:
                href = self.get_url(addr) + chunk
            if addr in ('history', 'search'):
                class_ = 'special'
            elif addr not in self.wiki.storage:
                class_ = 'nonexistent'
        return werkzeug.html.a(image or text, href=href, class_=class_,
                               title=addr)

    def wiki_image(self, addr, alt, class_='wiki'):
        """Create HTML for a wiki image."""

        html = werkzeug.html
        chunk = ''
        if external_link(addr):
            return html.img(src=werkzeug.url_fix(addr), class_="external",
                            alt=alt)
        if '#' in addr:
            addr, chunk = addr.split('#', 1)
        if addr == '':
            return html.a(name=chunk)
        if addr in self.wiki.storage:
            mime = self.wiki.storage.page_mime(addr)
            if mime.startswith('image/'):
                return html.img(src=self.get_download_url(addr), class_=class_,
                                alt=alt)
            else:
                return html.img(href=self.get_download_url(addr), alt=alt)
        else:
            return html.a(html(alt), href=self.get_url(addr))

    def html_head(self, title, robots=False, edit_button=False):
        html = werkzeug.html

        yield html.title(html(u'%s - %s' % (title, self.config.site_name)))
        if self.config.style_page in self.wiki.storage:
            yield html.link(rel="stylesheet", type_="text/css",
                href=self.get_download_url(self.config.style_page))
        else:
            yield html.style(html(self.config.default_style),
                             type_="text/css")

        if not robots:
            yield html.meta(name="robots", content="NOINDEX,NOFOLLOW")

        if edit_button:
            yield html.link(rel="alternate", type_="application/wiki",
                            href=self.get_url(self.title, self.wiki.edit))

        yield html.link(rel="shortcut icon", type_="image/x-icon",
                        href=self.get_url(None, self.wiki.favicon))
        yield html.link(rel="alternate", type_="application/rss+xml",
                        title=u"%s (RSS)" % self.config.site_name,
                        href=self.get_url(None, self.wiki.rss))
        yield html.link(rel="alternate", type_="application/rss+xml",
                        title="%s (ATOM)" % self.config.site_name,
                         href=self.get_url(None, self.wiki.atom))
        yield self.config.html_head

    def search_form(self):
        html = werkzeug.html
        return html.form(html.div(html.input(name="q", class_="search"),
                html.input(class_="button", type_="submit", value=_(u'Search')),
            ), method="GET", class_="search",
            action=self.get_url(None, self.wiki.search))

    def logo(self):
        html = werkzeug.html
        return html.a(html.img(alt=u"[%s]" % self.config.front_page,
            src=self.get_download_url(self.config.logo_page)),
            class_='logo', href=self.get_url(self.config.front_page))

    def menu(self):
        html = werkzeug.html
        if self.config.menu_page in self.wiki.storage:
            items = self.wiki.index.page_links_and_labels(self.config.menu_page)
        else:
            items = [
                (self.wiki.config.front_page, self.wiki.config.front_page),
                ('history', _(u'Recent changes')),
            ]
        for link, label in items:
            if link == self.title:
                yield html.a(label, href=self.get_url(link), class_="current")
            else:
                yield html.a(label, href=self.get_url(link))

    def header(self, special_title):
        html = werkzeug.html
        if self.config.logo_page in self.wiki.storage:
            yield self.logo()
        yield self.search_form()
        yield html.div(u" ".join(self.menu()), class_="menu")
        yield html.h1(html(special_title or self.title))

    def footer(self):
        html = werkzeug.html
        try:
            self.wiki.check_lock(self.title)
            yield html.a(html(_(u'Edit')), class_="edit",
                         href=self.get_url(self.title, self.wiki.edit))
        except werkzeug.exceptions.Forbidden:
            pass
        yield html.a(html(_(u'History')), class_="history",
                     href=self.get_url(self.title, self.wiki.history))
        yield html.a(html(_(u'Backlinks')), class_="backlinks",
                     href=self.get_url(self.title, self.wiki.backlinks))

    def page(self, content, special_title, footer=False):
        html = werkzeug.html
        yield html.div(class_="header", *self.header(special_title))
        yield u'<div class="content">'
        for part in content:
            yield part
        if not special_title:
            yield html.div(u" ".join(self.footer()), class_="footer")
        yield u'</div>'

    def render_content(self, content, special_title=None):
        """The main page template."""

        html = werkzeug.html
        yield (u'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
               '"http://www.w3.org/TR/html4/strict.dtd"><html>')
        if special_title:
            yield html.head(*self.html_head(special_title))
        else:
            yield html.head(*self.html_head(self.title, robots=True,
                                            edit_button=True))
        yield u'<body>'
        for part in self.page(content, special_title):
            yield part
        if self.config.js_editor:
            try:
                self.wiki.check_lock(self.title)
                yield html.script(u"""
var tagList = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre', 'ul', 'div'];
var baseUrl = '%s';
for (var j = 0; j < tagList.length; ++j) {
    var tags = document.getElementsByTagName(tagList[j]);
    for (var i = 0; i < tags.length; ++i) {
        var tag = tags[i];
        if (tag.id && tag.id.match(/^line_\d+$/)) {
            tag.ondblclick = function () {
                var url = baseUrl+'#'+this.id.replace('line_', '');
                document.location.href = url;
            };
        }
    }
};
""" % self.request.get_url(self.title, self.wiki.edit))
            except werkzeug.exceptions.Forbidden:
                pass
        yield u'</body></html>'


class WikiTitleConverter(werkzeug.routing.PathConverter):
    """Behaves like the path converter, except that it escapes slashes."""

    def to_url(self, value):
        return werkzeug.url_quote(value, self.map.charset, safe="")

class Wiki(object):
    """
    The main class of the wiki, handling initialization of the whole
    application and most of the logic.
    """
    parser_class = WikiParser
    storage_class = WikiStorage
    index_class = WikiSearch

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
        self.storage = self.storage_class(self.path, self.config.page_charset)
        self.parser = self.parser_class
        if not os.path.isdir(self.cache):
            os.makedirs(self.cache)
            reindex = True
        else:
            reindex = False
        self.index = self.index_class(self.cache, self.config.language,
                                      self.storage, self.parser)
        R = werkzeug.routing.Rule
        self.url_map = werkzeug.routing.Map([
            R('/', defaults={'title': self.config.front_page},
              endpoint=self.view, methods=['GET', 'HEAD']),
            R('/edit/<title:title>', endpoint=self.edit, methods=['GET']),
            R('/edit/<title:title>', endpoint=self.save, methods=['POST']),
            R('/history/<title:title>', endpoint=self.history,
              methods=['GET', 'HEAD']),
            R('/undo/<title:title>', endpoint=self.undo, methods=['POST']),
            R('/history/', endpoint=self.recent_changes,
              methods=['GET', 'HEAD']),
            R('/history/<title:title>/<int:rev>', endpoint=self.revision,
              methods=['GET']),
            R('/history/<title>/<int:from_rev>:<int:to_rev>',
              endpoint=self.diff, methods=['GET']),
            R('/download/<title:title>', endpoint=self.download,
              methods=['GET', 'HEAD']),
            R('/<title:title>', endpoint=self.view, methods=['GET', 'HEAD']),
            R('/feed/rss', endpoint=self.rss, methods=['GET', 'HEAD']),
            R('/feed/atom', endpoint=self.atom, methods=['GET', 'HEAD']),
            R('/favicon.ico', endpoint=self.favicon, methods=['GET', 'HEAD']),
            R('/robots.txt', endpoint=self.robots, methods=['GET']),
            R('/search', endpoint=self.search, methods=['GET', 'POST']),
            R('/search/<title:title>', endpoint=self.backlinks,
              methods=['GET', 'POST']),
            R('/off-with-his-head', endpoint=self.die, methods=['GET']),
        ], converters={'title':WikiTitleConverter})

#    def html_page(self, request, title, content, page_title=u''):
#        page = WikiPage(self, request, title)
#        return page.render_content(content, page_title)

    def view(self, request, title):
        page = WikiPage(self, request, title)
        try:
            content = self.view_content(request, title, page)
        except werkzeug.exceptions.NotFound:
            url = request.get_url(title, self.edit, external=True)
            return werkzeug.routing.redirect(url, code=303)
        html = page.render_content(content)

        dependencies = []
        unique_titles = set()
        config_pages = [
            self.config.style_page,
            self.config.logo_page,
            self.config.menu_page,
        ]
        linked_pages = self.index.page_links(title)
        for link_title in itertools.chain(linked_pages, config_pages):
            if link_title not in self.storage and title not in unique_titles:
                unique_titles.add(link_title)
                dependencies.append(u'%s' % werkzeug.url_quote(link_title))
        etag = '/(%s)' % u','.join(dependencies)

        return self.response(request, title, html, etag=etag)

    def view_content(self, request, title, page, lines=None):
        mime = self.storage.page_mime(title)
        if mime == 'text/x-wiki':
            if lines is None:
                page_file = self.storage.open_page(title)
                lines = self.storage.page_lines(page_file)
            content = self.parser(lines, page.wiki_link, page.wiki_image,
                                  self.highlight, self.wiki_math)
        elif mime.startswith('image/'):
            if title not in self.storage:
                raise werkzeug.exceptions.NotFound()
            content = ['<img src="%s" alt="%s">'
                       % (request.get_download_url(title),
                          werkzeug.escape(title))]
        elif mime.startswith('text/'):
            if lines is None:
                text = self.storage.page_text(title)
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
        page = WikiPage(self, request, title)
        html = page.render_content(content, special_title)
        response = self.response(request, title, html, rev=rev, etag='/old')
        return response

    def check_lock(self, title):
        if self.config.read_only:
            raise werkzeug.exceptions.Forbidden()
        if self.config.locked_page in self.storage:
            if title in self.index.page_links(self.config.locked_page):
                raise werkzeug.exceptions.Forbidden()

    def save(self, request, title):
        self.check_lock(title)
        url = request.get_url(title)
        if request.form.get('cancel'):
            if title not in self.storage:
                url = request.get_url(self.config.front_page)
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
            if text is not None:
                if title == self.config.locked_page:
                    for link, label in self.extract_links(text):
                        if title == link:
                            raise werkzeug.exceptions.Forbidden()
                if u'href="' in comment or u'http:' in comment:
                    raise werkzeug.exceptions.Forbidden()
                if text.strip() == '':
                    self.storage.delete_page(title, author, comment)
                    url = request.get_url(self.config.front_page)
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
                    url = request.get_url(self.config.front_page)
            self.index.update_page(title, text=text)
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
        content = form(request, title, preview)
        page = WikiPage(self, request, title)
        special_title = _(u'Editing "%(title)s"') % {'title': title}
        html = page.render_content(content, special_title)
        if title not in self.storage:
            return werkzeug.Response(html, mimetype="text/html",
                                     status='404 Not found')
        elif preview:
            return werkzeug.Response(html, mimetype="text/html")
        else:
            return self.response(request, title, html, '/edit')

    def highlight(self, text, mime=None, syntax=None, line_no=0):
        try:
            import pygments
            import pygments.util
            import pygments.lexers
            import pygments.formatters
            import pygments.styles
        except ImportError:
            yield werkzeug.html.pre(werkzeug.html(text))
            return
        if 'tango' in pygments.styles.STYLE_MAP:
            style = 'tango'
        else:
            style = 'friendly'
        formatter = pygments.formatters.HtmlFormatter(style=style)
        formatter.line_no = line_no
        def wrapper(source, outfile):
            yield 0, '<div class="highlight"><pre>'
            for lineno, line in source:
                yield lineno, werkzeug.html.div(line.strip('\n'),
                                                id_="line_%d" % formatter.line_no)
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
        except pygments.util.ClassNotFound:
            yield werkzeug.html.pre(werkzeug.html(text))
            return
        css = formatter.get_style_defs('.highlight')
        html = pygments.highlight(text, lexer, formatter)
        yield werkzeug.html.style(werkzeug.html(css), type="text/css")
        yield html

    def editor_form(self, request, title, preview=None):
        author = request.get_author()
        lines = []
        try:
            page_file = self.storage.open_page(title)
            lines = self.storage.page_lines(page_file)
            (rev, old_date, old_author,
                old_comment) = self.storage.page_meta(title)
            comment = _(u'modified')
            if old_author == author:
                comment = old_comment
        except werkzeug.exceptions.NotFound:
            comment = _(u'created')
            rev = -1
        if preview:
            lines = preview
            comment = request.form.get('comment', comment)
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
            value=request.get_author()), class_="comment")
        yield html.div(
                html.input(type_="submit", name="save", value=_(u'Save')),
                html.input(type_="submit", name="preview", value=_(u'Preview')),
                html.input(type_="submit", name="cancel", value=_(u'Cancel')),
                class_="buttons")
        yield u'</div></form>'
        if preview:
            yield html.h1(html(_(u'Preview, not saved')), class_="preview")
            page = WikiPage(self, request, title)
            for part in self.view_content(request, title, page, preview):
                yield part


        if self.config.js_editor:
            # Scroll the textarea to the line specified
            # Move the cursor to the specified line
            yield html.script(ur"""
var jumpLine = 0+document.location.hash.substring(1);
if (jumpLine) {
    var textBox = document.getElementById('editortext');
    var textLines = textBox.textContent.match(/(.*\n)/g);
    var scrolledText = '';
    for (var i = 0; i < textLines.length && i < jumpLine; ++i) {
        scrolledText += textLines[i];
    }
    textBox.focus();
    if (textBox.setSelectionRange) {
        textBox.setSelectionRange(scrolledText.length, scrolledText.length);
    } else if (textBox.createTextRange) {
        var range = textBox.createTextRange();
        range.collapse(true);
        range.moveEnd('character', scrolledText.length);
        range.moveStart('character', scrolledText.length);
        range.select();
    }
    var scrollPre = document.createElement('pre');
    textBox.parentNode.appendChild(scrollPre);
    var style = window.getComputedStyle(textBox, '');
    scrollPre.style.font = style.font;
    scrollPre.style.border = style.border;
    scrollPre.style.outline = style.outline;
    scrollPre.style.lineHeight = style.lineHeight;
    scrollPre.style.letterSpacing = style.letterSpacing;
    scrollPre.style.fontFamily = style.fontFamily;
    scrollPre.style.fontSize = style.fontSize;
    scrollPre.style.padding = 0;
    scrollPre.style.overflow = 'scroll';
    try { scrollPre.style.whiteSpace = "-moz-pre-wrap" } catch(e) {};
    try { scrollPre.style.whiteSpace = "-o-pre-wrap" } catch(e) {};
    try { scrollPre.style.whiteSpace = "-pre-wrap" } catch(e) {};
    try { scrollPre.style.whiteSpace = "pre-wrap" } catch(e) {};
    scrollPre.textContent = scrolledText;
    textBox.scrollTop = scrollPre.scrollHeight;
    scrollPre.parentNode.removeChild(scrollPre);
}
""")

    def upload_form(self, request, title, preview=None):
        author = request.get_author()
        if title in self.storage:
            comment = _(u'changed')
            (rev, old_date, old_author,
                old_comment) = self.storage.page_meta(title)
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
            html.label(html(_(u'Comment')),
                       html.input(name="comment", value=comment)),
            html.label(html(_(u'Author')),
                       html.input(name="author", value=author)),
            html.div(
                html.input(type_="submit", name="save", value=_(u'Save')),
                html.input(type_="submit", name="cancel", value=_(u'Cancel')),
                class_="buttons")), action="", method="POST", class_="editor",
                                    enctype="multipart/form-data")

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
            try:
                parent = int(request.form.get("parent"))
            except (ValueError, TypeError):
                parent = None
            if rev == 0:
                comment = _(u'Delete page %(title)s') % {'title': title}
                data = ''
                self.storage.delete_page(title, author, comment)
            else:
                comment = _(u'Undo of change %(rev)d of page %(title)s') % {
                    'rev': rev, 'title': title}
                data = self.storage.page_revision(title, rev-1)
                self.storage.save_data(title, data, author, comment, parent)
            self.index.update_page(title, data=data)
        url = request.adapter.build(self.history, {'title': title},
                                    method='GET', force_external=True)
        return werkzeug.redirect(url, 303)

    def history(self, request, title):
        page = WikiPage(self, request, title)
        content = page.render_content(self.history_list(request, title),
            _(u'History of "%(title)s"') % {'title': title})
        response = self.response(request, title, content, '/history')
        return response

    def history_list(self, request, title):
        max_rev = -1;
        link = werkzeug.html.a(werkzeug.html(title),
                               href=request.get_url(title))
        yield werkzeug.html.p(
            _(u'History of changes for %(link)s.') % {'link': link})
        url = request.adapter.build(self.undo, {'title': title}, method='POST')
        yield u'<form action="%s" method="POST"><ul class="history">' % url
        for rev, date, author, comment in self.storage.page_history(title):
            if max_rev < 0:
                max_rev = rev
            if rev > 0:
                url = request.adapter.build(self.diff, {
                    'title': title, 'from_rev': rev-1, 'to_rev': rev})
            else:
                url = request.adapter.build(self.revision, {
                    'title': title, 'rev': rev})
            yield u'<li>'
            yield werkzeug.html.a(date.strftime('%F %H:%M'), href=url)
            if not self.config.read_only:
                yield (u'<input type="submit" name="%d" value="Undo" '
                       u'class="button">' % rev)
            yield u' . . . . '
            yield werkzeug.html.a(werkzeug.html(author),
                                  href=request.get_url(author))
            yield u'<div class="comment">%s</div>' % werkzeug.escape(comment)
            yield u'</li>'
        yield u'</ul>'
        yield u'<input type="hidden" name="parent" value="%d">' % max_rev
        yield u'</form>'

    def recent_changes(self, request):
        page = WikiPage(self, request, u'history')
        content = page.render_content(self.changes_list(request),
            _(u'Recent changes'))
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
            yield werkzeug.html.a(werkzeug.html(title), href=request.get_url(title))
            yield u' . . . . '
            yield werkzeug.html.a(werkzeug.html(author), href=request.get_url(author))
            yield u'<div class="comment">%s</div>' % werkzeug.escape(comment)
            yield u'</li>'
        yield u'</ul>'

    def diff(self, request, title, from_rev, to_rev):
        from_page = self.storage.revision_text(title, from_rev)
        to_page = self.storage.revision_text(title, to_rev)
        from_url = request.adapter.build(self.revision,
                                         {'title': title, 'rev': from_rev})
        to_url = request.adapter.build(self.revision,
                                       {'title': title, 'rev': to_rev})
        content = itertools.chain(
            [werkzeug.html.p(werkzeug.html(_(u'Differences between revisions '
                u'%(link1)s and %(link2)s of page %(link)s.')) % {
                'link1': werkzeug.html.a(str(from_rev), href=from_url),
                'link2': werkzeug.html.a(str(to_rev), href=to_url),
                'link': werkzeug.html.a(werkzeug.html(title), href=request.get_url(title))
            })],
            self.diff_content(from_page, to_page))
        page = WikiPage(self, request, title)
        special_title=_(u'Diff for "%(title)s"') % {'title': title}
        html = page.render_content(content, special_title)
        response = werkzeug.Response(html, mimetype='text/html')
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
        page = WikiPage(self, request, '')
        html = page.render_content(content, title)
        return WikiResponse(html, mimetype='text/html')

    def page_index(self, request):
        yield u'<p>%s</p>' % werkzeug.escape(_(u'Index of all pages.'))
        yield u'<ul>'
        for title in sorted(self.storage.all_pages()):
            yield werkzeug.html.li(werkzeug.html.a(werkzeug.html(title),
                                                   href=request.get_url(title)))
        yield u'</ul>'

    def page_search(self, request, words):
        result = sorted(self.index.find(words), key=lambda x:-x[0])
        yield werkzeug.html.p(
            _(u'%d page(s) containing all words:') % len(result))
        yield u'<ul>'
        for score, title in result:
            try:
                snippet = self.search_snippet(title, words)
                link = werkzeug.html.a(werkzeug.html(title),
                                       href=request.get_url(title))
                yield ('<li><b>%s</b> (%d)<div class="snippet">%s</div></li>'
                       % (link, score, snippet))
            except werkzeug.exceptions.NotFound:
                pass
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
        page = WikiPage(self, request, title)
        html = page.render_content(content, _(u'Links to "%s"') % title)
        response = werkzeug.Response(html, mimetype='text/html')
        response.set_etag('/backlinks/%d' % self.storage.repo_revision())
        response.make_conditional(request)
        return response

    def page_backlinks(self, request, title):
        yield u'<p>%s</p>' % (_(u'Pages that contain a link to %s.')
            % werkzeug.html.a(werkzeug.html(title),
                              href=request.get_url(title)))
        yield u'<ul>'
        for link in self.index.page_backlinks(title):
            yield '<li>%s</li>' % werkzeug.html.a(werkzeug.html(link),
                                                  href=request.get_url(link))
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
                return err
        finally:
            request.cleanup()
            del request
            del adapter

def main():
    """
    Starts a standalone WSGI server.
    """

    import wsgiref.simple_server

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
    config.parse_files()
    config.sanitize()
    host, port = config.interface, int(config.port)
    wiki = Wiki(config)
    server = wsgiref.simple_server.make_server(host, port, wiki.application)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
