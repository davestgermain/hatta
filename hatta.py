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
import datetime
import difflib
import itertools
import imghdr
import mimetypes
import os
import re
import shelve
import tempfile
import urllib
import weakref


import werkzeug
os.environ['HGENCODING'] = 'utf-8'
os.environ["HGMERGE"] = "internal:merge"
import mercurial.hg
import mercurial.ui
import mercurial.revlog

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
            os.rename(file_name, file_path)
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

    def page_date(self, title):
        stamp = os.path.getmtime(self._file_path(title))
        return datetime.datetime.fromtimestamp(stamp)

    def page_size(self, title):
        (st_mode, st_ino, st_dev, st_nlink, st_uid, st_gid, st_size, st_atime,
         st_mtime, st_ctime) = os.stat(self._file_path(title))
        return st_size

    def page_meta(self, title):
        filectx_tip = self._find_filectx(title)
        if filectx_tip is None:
            return -1, None, u'', u''
        rev = filectx_tip.filerev()
        filectx = filectx_tip.filectx(rev)
        date = datetime.datetime.fromtimestamp(filectx.date()[0])
        author = unicode(filectx.user(), "utf-8",
                         'replace').split('<')[0].strip()
        comment = unicode(filectx.description(), "utf-8", 'replace')
        if filectx_tip is None:
            return -1, None, u'', u''
        return rev, date, author, comment

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
            inside = self.line_image(match.groupdict())
        else:
            inside = werkzeug.escape(text)
        return self.wiki_link(target, text, image=inside)

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
            return self.wiki_syntax(inside, syntax=syntax)

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

    def parse(self, lines, wiki_link=None, wiki_image=None, wiki_syntax=None):
        def key(line):
            match = self.block_re.match(line)
            if match:
                return match.lastgroup
            return "paragraph"
        self.lines = (unicode(line, "utf-8", "replace") for line in lines)
        self.stack = []
        self.wiki_link = wiki_link
        self.wiki_image = wiki_image
        self.wiki_syntax = wiki_syntax
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
between beyond bill both bottom but by can cannot cant con could couldnt
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
[A-ZĄÂÃĀÄÅÁÀĂĘÉÊĚËĒÈŚĆÇČŁÓÒÖŌÕÔŃŻŹŽÑÍÏĐÞÐÆŸ]
[a-ząâãāäåáàăęéêěëēèśćçčłóòöōõôńżźžñíïđþðæÿ]+
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
        words = self.count_words(self.filter_words(self.split_text(text)))
        for word, count in words.iteritems():
            encoded = word.encode("utf-8")
            if encoded not in self.index:
                stored = {}
            else:
                stored = self.index[encoded]
            stored[ident] = count
            self.index[encoded] = stored
        self.index.sync()

    def _extract_links(self, text, parser):
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

            def empty(*args, **kw):
                return u''

        helper = LinkExtractor()
        lines = text.split('\n')
        for part in parser.parse(lines, helper.wiki_link,
                                 helper.wiki_image, helper.empty):
            pass
        return helper.links, helper.link_labels

    def add_links(self, title, text, parser):
        links, labels = self._extract_links(text, parser)
        self.links[title.encode('utf-8', 'backslashreplace')] = links
        self.links.sync()
        self.labels[title.encode('utf-8', 'backslashreplace')] = labels
        self.labels.sync()

    def regenerate_backlinks(self):
        for key in self.backlinks:
            del self.backlinks[key]
        for title, links in self.links.iteritems():
            ident = self.get_title_id(title)
            for link in links:
                encoded = link.encode('utf-8', 'backslashreplace')
                backlinks = self.backlinks.get(encoded, [])
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
        self.links = []

    def get_page_url(self, title):
        return self.adapter.build(self.wiki.view, {'title': title},
                                  method='GET')

    def get_download_url(self, title):
        return self.adapter.build(self.wiki.download, {'title': title},
                                  method='GET')

    def wiki_link(self, addr, label, class_='wiki', image=None):
        if external_link(addr):
            return u'<a href="%s" class="external">%s</a>' % (
                werkzeug.url_fix(addr), werkzeug.escape(label))
        if '#' in addr:
            addr, chunk = addr.split('#', 1)
            chunk = '#%s' % chunk
        else:
            chunk = ''
        if addr == u'':
            return u'<a href="%s" class="%s">%s</a>' % (
                chunk, class_, image or werkzeug.escape(label))
        self.links.append(addr)
        if addr in self.wiki.storage:
            return u'<a href="%s%s" class="%s">%s</a>' % (
                self.get_page_url(addr), chunk, class_,
                image or werkzeug.escape(label))
        else:
            return u'<a href="%s%s" class="nonexistent">%s</a>' % (
                self.get_page_url(addr), chunk, werkzeug.escape(label))

    def wiki_image(self, addr, alt, class_='wiki'):
        if external_link(addr):
            return u'<img src="%s" class="external" alt="%s">' % (
                werkzeug.url_fix(addr), werkzeug.escape(alt))
        if '#' in addr:
            addr, chunk = addr.split('#', 1)
        self.links.append(addr)
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

class WikiTitle(werkzeug.routing.BaseConverter):
    def to_python(self, value):
        # XXX work around a bug in Werkzeug
        return unicode(urllib.unquote_plus(value.encode('utf-8', 'ignore')),
                       'utf-8', 'ignore')

    def to_url(self, value):
        #return werkzeug.url_quote_plus(value.encode('utf-8', 'ignore'), safe='')
        return unicode(urllib.quote_plus(value.encode('utf-8', 'ignore'),
                                         safe=''), 'utf-8', 'ignore')

class WikiRedirect(werkzeug.routing.RequestRedirect):
    code = 303
    def get_response(self, environ):
        return werkzeug.redirect(self.new_url, 303)

class Wiki(object):
    site_name = 'Hatta Wiki'
    front_page = 'Home'
    style_page = 'style.css'
    logo_page = 'logo.png'
    menu_page = 'Menu'
    locked_page = 'Locked'
    alias_page = 'Alias'
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
hr { background: transparent; border:none; height: 0; border-bottom: 1px solid #babdb6; clear: both }
"""
    icon = '\x00\x00\x01\x00\x01\x00\x10\x10\x10\x00\x01\x00\x04\x00(\x01\x00\x00\x16\x00\x00\x00(\x00\x00\x00\x10\x00\x00\x00 \x00\x00\x00\x01\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x0064.\x00SWU\x00\x85\x8a\x88\x00\xcf\xd7\xd3\x00\xec\xee\xee\x00\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00b\x11\x11\x11\x11\x11\x11\x16bUUUUUU\x16bTDDB\x02E\x16bTBD@0E\x16bTD\x14@@E\x16bTD@A\x02E\x16bTDD\x03\x04E\x16bR\x02  05\x16bS\x03\x03\x04\x14E\x16bT\x04\x04\x04BE\x16bT\x04\x04\x04DE\x16bR\x04\x03\x04DE\x16bS\x14 $DE\x16bTDDDDE\x16bUUUUUU\x16c""""""&\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00\x80\x01\x00\x00'

    def __init__(self, path='docs/', cache='cache/'):
        self.path = os.path.abspath(path)
        self.cache = os.path.abspath(cache)
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
            werkzeug.routing.Rule('/', defaults={'title': self.front_page},
                                  endpoint=self.view,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/edit/<title:title>', endpoint=self.edit,
                                  methods=['GET']),
            werkzeug.routing.Rule('/edit/<title:title>', endpoint=self.save,
                                  methods=['POST']),
            werkzeug.routing.Rule('/history/<title:title>', endpoint=self.history,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/history/<title:title>', endpoint=self.undo,
                                  methods=['POST']),
            werkzeug.routing.Rule('/history/', endpoint=self.recent_changes,
                                  methods=['GET', 'HEAD']),
            werkzeug.routing.Rule('/history/<title:title>/<int:rev>',
                                  endpoint=self.revision, methods=['GET']),
            werkzeug.routing.Rule('/history/<title:title>/<int:from_rev>:<int:to_rev>',
                                  endpoint=self.diff, methods=['GET']),
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
            werkzeug.routing.Rule('/search', endpoint=self.search,
                                  methods=['GET', 'POST']),
            werkzeug.routing.Rule('/search/<title:title>', endpoint=self.backlinks,
                                  methods=['GET', 'POST']),
        ], converters={'title':WikiTitle})

    def html_page(self, request, title, content, page_title=u''):
        rss = request.adapter.build(self.rss)
        icon = request.adapter.build(self.favicon)
        yield (u'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
               '"http://www.w3.org/TR/html4/strict.dtd">')
        yield u'<html><head><title>%s - %s</title>' % (werkzeug.escape(page_title or title), werkzeug.escape(self.site_name))
        if self.style_page in self.storage:
            css = request.get_download_url(self.style_page)
            yield u'<link rel="stylesheet" type="text/css" href="%s">' % css
        else:
            yield u'<style type="text/css">%s</style>' % self.default_style
        yield u'<link rel="shortcut icon" type="image/x-icon" href="%s">' % icon
        if not page_title:
            edit = request.adapter.build(self.edit, {'title': title})
            yield u'<link rel="alternate" type="application/wiki" href="%s">' % edit
        yield (u'<link rel="alternate" type="application/rss+xml" '
               u'title="Recent Changes" href="%s">' % rss)
        yield u'</head><body><div class="header">'
        if self.logo_page in self.storage:
            home = request.get_page_url(self.front_page)
            logo = request.get_download_url(self.logo_page)
            yield u'<a href="%s" class="logo"><img src="%s" alt="[%s]"></a>' % (
                home, logo, werkzeug.escape(self.front_page))
        search = request.adapter.build(self.search)
        yield u'<form class="search" action="%s" method="GET"><div>' % search
        yield u'<input name="q" class="search">'
        yield u'<input class="button" type="submit" value="Search">'
        yield u'</div></form>'
        if self.menu_page in self.storage:
            menu = self.index.page_links(self.menu_page)
            labels = self.index.page_labels(self.menu_page)
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
            history = request.adapter.build(self.history, {'title': title})
            backlinks = request.adapter.build(self.backlinks, {'title': title})
            yield u'<div class="footer">'
            yield u'<a href="%s" class="edit">Edit</a> ' % edit
            yield u'<a href="%s" class="history">History</a> ' % history
            yield u'<a href="%s" class="history">Backlinks</a> ' % backlinks
            yield u'</div>'
        yield u'</div></body></html>'


    def view(self, request, title):
        if title not in self.storage:
            url = request.adapter.build(self.edit, {'title':title})
            raise WikiRedirect(url)
        mime = self.storage.page_mime(title)
        rev = None
        if mime == 'text/x-wiki':
            f = self.storage.open_page(title)
            content = self.parser.parse(f, request.wiki_link,
                               request.wiki_image, self.highlight)
            rev, date, author, comment = self.storage.page_meta(title)
            revs = ['%d' % rev]
            unique_titles = {}
            for link in self.index.page_links(title):
                if link not in self.storage and link not in unique_titles:
                    unique_titles[link] = True
                    revs.append(u'%s' % werkzeug.url_quote(link))
            rev = u','.join(revs)
        elif mime.startswith('image/'):
            content = ['<img src="%s" alt="%s">'
                       % (request.get_download_url(title),
                          werkzeug.escape(title))]
        elif mime.startswith('text/'):
            f = self.storage.open_page(title)
            text = f.read()
            f.close()
            content = self.highlight(text, mime=mime)
        else:
            content = ['<p>Download <a href="%s">%s</a> as <i>%s</i>.</p>'
                   % (request.get_download_url(title), werkzeug.escape(title),
                      mime)]
        html = self.html_page(request, title, content)
        response = self.response(request, title, html, rev=rev)
        return response

    def revision(self, request, title, rev):
        data = self.storage.page_revision(title, rev)
        content = [
            u'<p>Content of revision %d of page %s:</p>'
                % (rev, request.wiki_link(title, title)),
            u'<pre>%s</pre>'
                % werkzeug.escape(unicode(data, 'utf-8', 'replace')),
        ]
        html = self.html_page(request, title, content,
                              page_title=u'Revision of "%s"' % title)
        response = werkzeug.Response(html, mimetype="text/html")
        response = self.response(request, title, html, rev=rev)
        return response

    def check_lock(self, title):
        if self.locked_page in self.storage:
            if title in self.index.page_links(self.locked_page):
                raise werkzeug.exceptions.Forbidden()

    def save(self, request, title):
        self.check_lock(title)
        url = request.get_page_url(title)
        mime = self.storage.page_mime(title)
        if request.form.get('cancel'):
            if title not in self.storage:
                url = request.get_page_url(self.front_page)
        elif request.form.get('save'):
            comment = request.form.get("comment", "")
            author = request.get_author()
            text = request.form.get("text")
            if text is not None:
                data = text.encode('utf-8')
                if title == self.locked_page:
                    self.index.add_links(title, data, self.parser)
                    if title in self.index.page_links(self.locked_page):
                        raise werkzeug.exceptions.Forbidden()
                if text.strip() == '':
                    self.storage.delete_page(title, author, comment)
                    url = request.get_page_url(self.front_page)
                else:
                    self.storage.save_text(title, data, author, comment)
                if mime.startswith('text/'):
                    self.index.add_words(title, text)
                if mime == 'text/x-wiki':
                    self.index.add_links(title, data, self.parser)
                    self.index.regenerate_backlinks()
            else:
                f = request.files['data'].stream
                if f is not None:
                    try:
                        self.storage.save_file(title, f.tmpname, author,
                                               comment)
                    except AttributeError:
                        self.storage.save_text(title, f.read(), author,
                                               comment)
        response = werkzeug.routing.redirect(url, code=303)
        response.set_cookie('author',
                            werkzeug.url_quote(request.get_author()),
                            max_age=604800)
        return response

    def edit(self, request, title):
        self.check_lock(title)
        if title not in self.storage:
            status = '404 Not found'
        else:
            status = None
        if self.storage.page_mime(title).startswith('text/'):
            form = self.editor_form
        else:
            form = self.upload_form
        html = self.html_page(request, title, form(request, title),
                              page_title=u'Editing "%s"' % title)
        if title not in self.storage:
            return werkzeug.Response(html, mimetype="text/html", status=status)
        else:
            return self.response(request, title, html, '/edit')

    def highlight(self, text, mime=None, syntax=None):
        try:
            import pygments
            import pygments.util
            import pygments.lexers
            import pygments.formatters
            formatter = pygments.formatters.HtmlFormatter()
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

    def editor_form(self, request, title):
        author = request.get_author()
        try:
            f = self.storage.open_page(title)
            comment = 'modified'
            rev, old_date, old_author, old_comment = self.storage.page_meta(title)
            if old_author == author:
                comment = old_comment
        except werkzeug.exceptions.NotFound:
            f = []
            comment = 'created'
            rev = -1
        yield u'<form action="" method="POST" class="editor"><div>'
        yield u'<textarea name="text" cols="80" rows="20">'
        for part in f:
            yield werkzeug.escape(part)
        yield u"""</textarea>"""
        yield u'<input type="hidden" name="parent" value="%d">' % rev
        yield u'<label class="comment">Comment <input name="comment" value="%s"></label>' % werkzeug.escape(comment)
        yield u'<label>Author <input name="author" value="%s"></label>' % werkzeug.escape(request.get_author())
        yield u'<div class="buttons">'
        yield u'<input type="submit" name="save" value="Save">'
        yield u'<input type="submit" name="cancel" value="Cancel">'
        yield u'</div>'
        yield u'</div></form>'

    def upload_form(self, request, title):
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

    def rss(self, request):
        now = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")
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
            werkzeug.escape(self.site_name),
            request.adapter.build(self.rss),
            request.adapter.build(self.recent_changes),
            now,
        )
        rss_body = []
        first_date = now
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
        content = [rss_head]+rss_body+[u'</channel></rss>']
        return self.response(request, 'rss', content, '/rss', 'application/xml',
                             first_rev, first_date)

    def response(self, request, title, content, etag='', mime='text/html',
                 rev=None, date=None):
#        headers = {
#            'Cache-Control': 'max-age=60, public',
#            'Vary': 'Transfer-Encoding',
#            'Allow': 'GET, HEAD',
#        }
        response = WikiResponse(content, mimetype=mime)
        if rev is None:# or date is None:
            nrev, ndate, author, comment = self.storage.page_meta(title)
            if rev is None:
                rev = nrev
            if date is None:
                date = ndate
        response.set_etag(u'%s/%s/%s' % (etag, werkzeug.url_quote(title), rev))
#        response.expires = datetime.datetime.now()+datetime.timedelta(days=3)
#        response.last_modified = date
        response.make_conditional(request)
        return response

    def download(self, request, title):
        mime = self.storage.page_mime(title)
        if mime == 'text/x-wiki':
            mime = 'text/plain'
        f = self.storage.open_page(title)
        response = self.response(request, title, f, '/download', mime)
        response.content_length = self.storage.page_size(title)
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
            self.index.add_words(title, data)
            self.index.add_links(title, data, self.parser)
            self.index.regenerate_backlinks()
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
        yield u'<form action="" method="POST"><ul class="history">'
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
        from_page = self.storage.page_revision(title, from_rev)
        to_page = self.storage.page_revision(title, to_rev)
        content = self.html_page(request, title, itertools.chain(
            [u'<p>Differences between revisions %d and %d of page %s.</p>'
             % (from_rev, to_rev, request.wiki_link(title, title))],
            self.diff_content(from_page, to_page)),
            page_title=u'Diff for "%s"' % title)
        response = werkzeug.Response(content, mimetype='text/html')
        return response

    def diff_content(self, data, other_data):
        diff = difflib._mdiff(data.split('\n'), other_data.split('\n'))
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
                        yield (u'<del>%s</del>'
                               % werkzeug.escape(unicode(old.group(1),
                                                         'utf-8', 'replace')))
                        old = old_iter.next()
                    while new and new.group(1):
                        if buff:
                            yield werkzeug.escape(buff)
                            buff = u''
                        yield (u'<ins>%s</ins>'
                               % werkzeug.escape(unicode(new.group(1),
                                                         'utf-8', 'replace')))
                        new = new_iter.next()
                    if new:
                        buff += unicode(new.group(2), 'utf-8', 'replace')
                    old = old_iter.next()
                    new = new_iter.next()
                if buff:
                    yield werkzeug.escape(buff)
                yield u'</div>'
            else:
                yield (u'<div class="orig">%s</div>'
                       % werkzeug.escape(unicode(old_text, 'utf-8', 'replace')))
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
        return werkzeug.Response(self.icon, mimetype='image/x-icon')

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
                self.index.add_words(title, data)
                if mime == 'text/x-wiki':
                    self.index.add_links(title, data, self.parser)
        self.index.regenerate_backlinks()

    @werkzeug.responder
    def application(self, environ, start):
        adapter = self.url_map.bind_to_environ(environ)
        request = WikiRequest(self, adapter, environ)
        try:
            endpoint, values = adapter.match()
            response = endpoint(request, **values)
        except werkzeug.exceptions.HTTPException, e:
#            import traceback
#            traceback.print_exc()
            return e
        finally:
            request.cleanup()
        return response

if __name__ == "__main__":
    # You can change some internal config here.
    interface = ''
    port = 8080
    pages_path = 'docs'
    cache_path = 'cache'
    application = Wiki(pages_path, cache_path).application
    werkzeug.run_simple(interface, port, application, use_reloader=True)
