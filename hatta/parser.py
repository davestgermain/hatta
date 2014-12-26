#!/usr/bin/python
# -*- coding: utf-8 -*-

import itertools
import re
import sys
import unicodedata
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


class RuleSet(object):
    """Object used for registering functions for parsing rules."""

    def __init__(self, inherit_from=None):
        """New rule sets can be empty, or copied from other rule sets."""

        if inherit_from is not None:
            self.rules = dict(inherit_from.rules)
        else:
            self.rules = {}
        self.compiled_re = None

    def __call__(self, pattern, priority=100, name=None):
        """A decorator that registers the function as a rule."""

        def decorator(function):
            self.add_rule(function, pattern, priority, name)
            return function
        return decorator

    def add_rule(self, function, pattern, priority=100, name=None):
        """Register a function as a rule manually."""

        if name is None:
            function_name = function.__name__
        else:
            function_name = name
        self.rules[function_name] = (priority, pattern, function)

    def compile(self):
        """Prepare the registered rule patterns for parsing."""

        rules = sorted(self.rules.iteritems(), key=lambda x: x[1][0])
        self.compiled_re = re.compile(
            ur"|".join(
                ur"(?P<%s>%s)" % (function_name, pattern) for
                    (function_name, (priority, pattern, function)) in rules
            ), re.U)

    def match_one(self, text):
        """Find the first rule matching provided text."""

        match = self.compiled_re.match(text)
        if not match:
            return '', {}
        function_name = match.lastgroup
        params = match.groupdict()
        return function_name, params

    def match_all(self, text):
        """Find all rules matching provided text."""

        for match in self.compiled_re.finditer(text):
            function_name = match.lastgroup
            params = match.groupdict()
            yield function_name, params

    def parse(self, text, bind_to=None):
        """
        Find all matching rules and call corresponding functions.
        If bind_to is provided, it will call the methods of provided object.
        """

        for function_name, params in self.match_all(text):
            priority, pattern, function = self.rules[function_name]
            if bind_to is not None:
                function = getattr(bind_to, function.__name__)
            params = dict((str(k), v) for (k, v) in params.iteritems()
                          if v is not None and k not in self.rules)
            yield function(**params)


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

    block_rules = RuleSet()
    markup_rules = RuleSet()

    list_pat = ur"^\s*[*#]+\s+"
    heading_pat = ur"^\s*=+"
    quote_pat = ur"^[>]+\s+"
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
        """
        Prepare all the patterns for parsing. Needs to be called again
        after monkey-patching the parser.
        """

        self.quote_re = re.compile(self.quote_pat, re.U)
        self.heading_re = re.compile(self.heading_pat, re.U)
        self.list_re = re.compile(self.list_pat, re.U)
        self.code_close_re = re.compile(ur"^\}\}\}\s*$", re.U)
        self.macro_close_re = re.compile(ur"^>>\s*$", re.U)
        self.conflict_close_re = re.compile(ur"^>>>>>>> other\s*$", re.U)
        self.conflict_sep_re = re.compile(ur"^=======\s*$", re.U)
        self.display_math_close_re = re.compile(ur"^[$][$]\s*$", re.U)
        self.image_re = re.compile(self.image_pat, re.U)
        smileys = ur"|".join(re.escape(k) for k in self.smilies)
        smiley_pat = (ur"(^|\b|(?<=\s))(?P<smiley_face>%s)"
                      ur"((?=[\s.,:;!?)/&=+-])|$)" % smileys)
        self.markup_rules.add_rule(
                self._line_smiley, smiley_pat, 125)
        self.markup_rules.compile()
        self.block_rules.compile()

    def __iter__(self):
        return self.parse()

    @classmethod
    def extract_links(cls, text):
        links = []

        def link(addr, label=None, class_=None, image=None, alt=None,
                 lineno=0):
            addr = addr.strip()
            if external_link(addr):
                # Don't index external links
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
            name, params = self.block_rules.match_one(line)
            return name or "_block_paragraph"

        for kind, block in itertools.groupby(self.enumerated_lines, key):
            func = getattr(self, kind)
            for part in func(block):
                yield part

    def parse_line(self, line):
        """
        Find all the line-level markup and return HTML for it.

        """
        for part in self.markup_rules.parse(line, self):
            yield part

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

    @markup_rules(ur"(?P<table_cell>=?\|=?)", 140)
    def _line_table(self, table_cell):
        return table_cell

    @markup_rules(ur"\\\\", 70)
    def _line_linebreak(self):
        return u'<br>'

    # Added in .compile()
    def _line_smiley(self, smiley_face):
        try:
            url = self.smilies[smiley_face]
        except KeyError:
            url = ''
        return self.wiki_image(url, smiley_face, class_="smiley")

    @markup_rules(ur"[*][*]", 10)
    def _line_bold(self):
        if 'b' in self.stack:
            return self.pop_to('b')
        else:
            self.stack.append('b')
            return u"<b>"

    @markup_rules(ur"//", 40)
    def _line_italic(self):
        if 'i' in self.stack:
            return self.pop_to('i')
        else:
            self.stack.append('i')
            return u"<i>"

    @markup_rules(ur"##", 110)
    def _line_mono(self):
        if 'tt' in self.stack:
            return self.pop_to('tt')
        else:
            self.stack.append('tt')
            return u"<tt>"

    @markup_rules(ur'(?P<punct>'
                  ur'(^|\b|(?<=\s))(%s)((?=[\s.,:;!?)/&=+"\'—-])|\b|$))' %
                  ur"|".join(re.escape(k) for k in punct), 130)
    def _line_punct(self, punct):
        return self.punct.get(punct, punct)

    @markup_rules(ur"\n", 120)
    def _line_newline(self):
        return "\n"

    @markup_rules(ur"(?P<plain_text>.+?)", 150)
    def _line_text(self, plain_text):
        return werkzeug.escape(plain_text)

    @markup_rules(ur"\$\$(?P<math_text>[^$]+)\$\$", 100)
    def _line_math(self, math_text):
        if self.wiki_math:
            math_text = self.wiki_math(math_text, False)
        else:
            math_text = werkzeug.escape(math_text)
        return werkzeug.html.var(math_text, class_="inline-math")

    @markup_rules(ur"[{][{][{](?P<code_text>([^}]|[^}][}]|[^}][}][}])"
                  ur"*[}]*)[}][}][}]", 20)
    def _line_code(self, code_text):
        return u'<code>%s</code>' % werkzeug.escape(code_text)

    @markup_rules(ur"""(?P<link_url>[a-zA-Z]+://\S+[^\s.,:;!?()'"\*/=+<>-])""", 30)
    def _line_free_link(self, link_url):
        return self._line_link(link_target=link_url)

    @markup_rules(ur"""(?P<mail_address>(mailto:)?"""
                  ur"""[^\s()\[\]<>{}"']+@\S+(\.[^\s.,:;!?()'"\*/=+<>-]+)+)""" , 90)
    def _line_mail(self, mail_address):
        text = mail_address
        if mail_address.startswith(u'mailto:'):
            text = text[len('mailto:'):]
        else:
            mail_address = u'mailto:%s' % mail_address
        return self._line_link(link_text=text, link_target=mail_address)

    @markup_rules(ur"\[\[(?P<link_target>([^|\]]|\][^|\]])+)"
                  ur"(\|(?P<link_text>([^\]]|\][^\]])+))?\]\]", 50)
    def _line_link(self, link_target, link_text=None):
        if not link_text:
            link_text = link_target
            if '#' in link_text:
                link_text, chunk = link_text.split('#', 1)
        match = self.image_re.match(link_text)
        if match:
            params = dict((str(k), v) for (k, v) in
                          match.groupdict().iteritems())
            image = self._line_image(**params)
            return self.wiki_link(link_target, link_text, image=image)
        return self.wiki_link(link_target, link_text)

    @markup_rules(image_pat, 60)
    def _line_image(self, image_target, image_text=None):
        if image_text is None:
            image_text = image_target
        return self.wiki_image(image_target, image_text)

    @markup_rules(ur"[<][<](?P<macro_name>\w+)\s+"
                  ur"(?P<macro_text>([^>]|[^>][>])+)[>][>]", 80)
    def _line_macro(self, macro_name, macro_text):
        macro_text = macro_text.strip()
        return u'<span class="%s">%s</span>' % (
            werkzeug.escape(macro_name, quote=True),
            werkzeug.escape(macro_text))

# methods for the block (multiline) markup:

    @block_rules(r"^[$][$]\s*$", 25)
    def _block_display_math(self, block):
        for self.line_no, part in block:
            math_text = u"\n".join(self.lines_until(self.display_math_close_re))
            if self.wiki_math:
                math_text = self.wiki_math(math_text, True)
            else:
                math_text = werkzeug.escape(math_text)
            yield werkzeug.html.div(
                math_text,
                class_="display-math",
                id="line_%d" % self.line_no,
            )

    @block_rules(ur"^[{][{][{]+\s*$", 20)
    def _block_code(self, block):
        for self.line_no, part in block:
            inside = u"\n".join(self.lines_until(self.code_close_re))
            yield werkzeug.html.pre(werkzeug.html(inside), class_="code",
                                    id="line_%d" % self.line_no)

    @block_rules(ur"^\{\{\{\#![\w+#.-]+\s*$", 100)
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

    @block_rules(ur"^<<\w+\s*$", 70)
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

    @block_rules(ur"^[ \t]+", 60)
    def _block_indent(self, block):
        parts = []
        first_line = None
        for self.line_no, part in block:
            if first_line is None:
                first_line = self.line_no
            parts.append(part.rstrip())
        text = u"\n".join(parts)
        yield werkzeug.html.pre(werkzeug.html(text), id="line_%d" % first_line)

    @block_rules(ur"^\|", 110)
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

    @block_rules(ur"^\s*$", 40)
    def _block_empty(self, block):
        yield u''

    @block_rules(ur"^\s*---+\s*$", 90)
    def _block_rule(self, block):
        for self.line_no, line in block:
            yield werkzeug.html.hr()

    @block_rules(heading_pat, 50)
    def _block_heading(self, block):
        for self.line_no, line in block:
            level = min(len(self.heading_re.match(line).group(0).strip()), 5)
            self.headings[level - 1] = self.headings.get(level - 1, 0) + 1
            label = u"-".join(str(self.headings.get(i, 0))
                              for i in range(level))
            yield werkzeug.html.a(name="head-%s" % label)
            yield u'<h%d id="line_%d">%s</h%d>' % (level, self.line_no,
                werkzeug.escape(line.strip("= \t\n\r\v")), level)

    @block_rules(list_pat, 10)
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
                yield '</li></%s>' % kind
                in_ul = False
                level -= 1
            if nest == level and not in_ul:
                yield '</li>'
            content = line.lstrip().lstrip('*#').strip()
            yield '<li>%s%s' % (u"".join(self.parse_line(content)),
                                self.pop_to(""))
            in_ul = False
        yield ('</li></%s>' % kind) * level

    @block_rules(quote_pat, 80)
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

    @block_rules(ur"^<<<<<<< local\s*$", 30)
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

    markup_rules = RuleSet(WikiParser.markup_rules)

    camel_link = ur"\w+[%s]\w+" % re.escape(
        u''.join(unichr(i) for i in xrange(sys.maxunicode)
        if unicodedata.category(unichr(i)) == 'Lu'))

    @markup_rules(ur'(?P<camel_link>%s)' % camel_link, 105)
    def _line_camel_link(self, camel_link):
        return self._line_link(link_target=camel_link)

    @markup_rules(ur"[!~](?P<camel_text>%s)" % camel_link, 106)
    def _line_camel_nolink(self, camel_text):
        return werkzeug.escape(camel_text)
