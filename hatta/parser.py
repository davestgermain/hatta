#!/usr/bin/python
# -*- coding: utf-8 -*-

import re
import sys
import unicodedata
import itertools
import werkzeug


EXTERNAL_URL_RE = re.compile(ur'^[a-z]+://|^mailto:', re.I | re.U)


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

    return EXTERNAL_URL_RE.match(addr)


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


    """

    list_pat = ur"^\s*[*#]+\s+"
    heading_pat = ur"^\s*=+"
    quote_pat = ur"^[>]+\s+"
    block = {
        # "name": (priority, ur"pattern"),
        "list": (10, list_pat),
        "code": (20, ur"^[{][{][{]+\s*$"),
        "conflict": (30, ur"^<<<<<<< local\s*$"),
        "empty": (40, ur"^\s*$"),
        "heading": (50, heading_pat),
        "indent": (60, ur"^[ \t]+"),
        "macro": (70, ur"^<<\w+\s*$"),
        "quote": (80, quote_pat),
        "rule": (90, ur"^\s*---+\s*$"),
        "syntax": (100, ur"^\{\{\{\#![\w+#.-]+\s*$"),
        "table": (110, ur"^\|"),
    }
    image_pat = (ur"\{\{(?P<image_target>([^|}]|}[^|}])*)"
                 ur"(\|(?P<image_text>([^}]|}[^}])*))?}}")
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
        # "name": (priority, ur"pattern"),
        "bold": (10, ur"[*][*]"),
        "code": (20, ur"[{][{][{](?P<code_text>([^}]|[^}][}]|[^}][}][}])"
                ur"*[}]*)[}][}][}]"),
        "free_link": (30, ur"""[a-zA-Z]+://\S+[^\s.,:;!?()'"=+<>-]"""),
        "italic": (40, ur"//"),
        "link": (50, ur"\[\[(?P<link_target>([^|\]]|\][^|\]])+)"
                ur"(\|(?P<link_text>([^\]]|\][^\]])+))?\]\]"),
        "image": (60, image_pat),
        "linebreak": (70, ur"\\\\"),
        "macro": (80, ur"[<][<](?P<macro_name>\w+)\s+"
                 ur"(?P<macro_text>([^>]|[^>][>])+)[>][>]"),
        "mail": (90, ur"""(mailto:)?\S+@\S+(\.[^\s.,:;!?()'"/=+<>-]+)+"""),
        "math": (100, ur"\$\$(?P<math_text>[^$]+)\$\$"),
        "mono": (110, ur"##"),
        "newline": (120, ur"\n"),
        "punct": (130,
                  ur'(^|\b|(?<=\s))(%s)((?=[\s.,:;!?)/&=+"\'—-])|\b|$)' %
                  ur"|".join(re.escape(k) for k in punct)),
        "table": (140, ur"=?\|=?"),
        "text": (150, ur".+?"),
    }

    def __init__(self, lines, wiki_link, wiki_image,
                 wiki_syntax=None, wiki_math=None, smilies=None):
        self.wiki_link = wiki_link
        self.wiki_image = wiki_image
        self.wiki_syntax = wiki_syntax
        self.wiki_math = wiki_math
        self.enumerated_lines = enumerate(lines)
        if smilies is not None:
            self.smilies = smilies
        self.compile_patterns()
        self.headings = {}
        self.stack = []
        self.line_no = 0

    def compile_patterns(self):
        self.quote_re = re.compile(self.quote_pat, re.U)
        self.heading_re = re.compile(self.heading_pat, re.U)
        self.list_re = re.compile(self.list_pat, re.U)
        patterns = ((k, p) for (k, (x, p)) in
                    sorted(self.block.iteritems(), key=lambda x: x[1][0]))
        self.block_re = re.compile(ur"|".join("(?P<%s>%s)" % pat
                                   for pat in patterns), re.U)
        self.code_close_re = re.compile(ur"^\}\}\}\s*$", re.U)
        self.macro_close_re = re.compile(ur"^>>\s*$", re.U)
        self.conflict_close_re = re.compile(ur"^>>>>>>> other\s*$", re.U)
        self.conflict_sep_re = re.compile(ur"^=======\s*$", re.U)
        self.image_re = re.compile(self.image_pat, re.U)
        smileys = ur"|".join(re.escape(k) for k in self.smilies)
        smiley_pat = (ur"(^|\b|(?<=\s))(?P<smiley_face>%s)"
                      ur"((?=[\s.,:;!?)/&=+-])|$)" % smileys)
        self.markup['smiley'] = (125, smiley_pat)
        patterns = ((k, p) for (k, (x, p)) in
                    sorted(self.markup.iteritems(), key=lambda x: x[1][0]))
        self.markup_re = re.compile(ur"|".join("(?P<%s>%s)" % pat
                                    for pat in patterns), re.U)

    def __iter__(self):
        return self.parse()

    @classmethod
    def extract_links(cls, text):
        links = []

        def link(addr, label=None, class_=None, image=None, alt=None,
                 lineno=0):
            addr = addr.strip()
            if external_link(addr) or addr.startswith(':'):
                # Don't index external links and aliases
                return u''
            if '#' in addr:
                addr, chunk = addr.split('#', 1)
            if addr == u'':
                return u''
            links.append((addr, label))
            return u''
        lines = text.split('\n')
        for part in cls(lines, link, link):
            for ret in links:
                yield ret
            links[:] = []

    def parse(self):
        """Parse a list of lines of wiki markup, yielding HTML for it."""

        self.headings = {}
        self.stack = []
        self.line_no = 0

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

        """

        for match in self.markup_re.finditer(line):
            func = getattr(self, "_line_%s" % match.lastgroup)
            yield func(match.groupdict())

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

    def _line_table(self, groups):
        return groups["table"]

    def _line_linebreak(self, groups):
        return u'<br>'

    def _line_smiley(self, groups):
        smiley = groups["smiley_face"]
        try:
            url = self.smilies[smiley]
        except KeyError:
            url = ''
        return self.wiki_image(url, smiley, class_="smiley")

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

    def _line_mono(self, groups):
        if 'tt' in self.stack:
            return self.pop_to('tt')
        else:
            self.stack.append('tt')
            return u"<tt>"

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
            in_cell = False
            in_th = False

            for part in self.parse_line(table_row):
                if part in ('=|', '|', '=|=', '|='):
                    if in_cell:
                        if in_th:
                            yield '</th>'
                        else:
                            yield '</td>'
                        in_cell = False
                    if part in ('=|=', '|='):
                        in_th = True
                    else:
                        in_th = False
                else:
                    if not in_cell:
                        if in_th:
                            yield '<th>'
                        else:
                            yield '<td>'
                        in_cell = True
                    yield part
            if in_cell:
                if in_th:
                    yield '</th>'
                else:
                    yield '</td>'
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
            self.headings[level - 1] = self.headings.get(level - 1, 0) + 1
            label = u"-".join(str(self.headings.get(i, 0))
                              for i in range(level))
            yield werkzeug.html.a(name="head-%s" % label)
            yield u'<h%d id="line_%d">%s</h%d>' % (level, self.line_no,
                werkzeug.escape(line.strip("= \t\n\r\v")), level)

    def _block_list(self, block):
        level = 0
        in_ul = False
        kind = None
        for self.line_no, line in block:
            bullets = self.list_re.match(line).group(0).strip()
            nest = len(bullets)
            if kind is None:
                if bullets.startswith('*'):
                    kind = 'ul'
                else:
                    kind = 'ol'
            while nest > level:
                if in_ul:
                    yield '<li>'
                yield '<%s id="line_%d">' % (kind, self.line_no)
                in_ul = True
                level += 1
            while nest < level:
                yield '</li></ul>'
                in_ul = False
                level -= 1
            if nest == level and not in_ul:
                yield '</li>'
            content = line.lstrip().lstrip('*#').strip()
            yield '<li>%s%s' % (u"".join(self.parse_line(content)),
                                self.pop_to(""))
            in_ul = False
        yield ('</li></%s>' % kind) * level

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
        yield '</blockquote>' * level

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


class WikiWikiParser(WikiParser):
    """A version of WikiParser that recognizes WikiWord links."""

    markup = dict(WikiParser.markup)
    camel_link = ur"\w+[%s]\w+" % re.escape(
        u''.join(unichr(i) for i in xrange(sys.maxunicode)
        if unicodedata.category(unichr(i)) == 'Lu'))
    markup["camel_link"] = (105, camel_link)
    markup["camel_nolink"] = (106, ur"[!~](?P<camel_text>%s)" % camel_link)

    def _line_camel_link(self, groups):
        groups['link_target'] = groups['camel_link']
        return self._line_link(groups)

    def _line_camel_nolink(self, groups):
        return werkzeug.escape(groups["camel_text"])
