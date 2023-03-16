#!/usr/bin/python
# -*- coding: utf-8 -*-

import itertools
import re
import sys
import unicodedata
from markupsafe import escape, Markup
from dominate import tags


EXTERNAL_URL_RE = re.compile(r'^[a-z]+://|^mailto:', re.I | re.U)


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

        rules = sorted(iter(self.rules.items()), key=lambda x: x[1][0])
        self.compiled_re = re.compile(
            r"|".join(
                r"(?P<%s>%s)" % (function_name, pattern) for
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
            params = dict((str(k), v) for (k, v) in params.items()
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

    list_pat = r"^\s*[*#]+\s+"
    heading_pat = r"^\s*=+"
    quote_pat = r"^[>]+\s+"
    image_pat = (r"\{\{(?P<image_target>([^|}]|}[^|}])*)"
                 r"(\|(?P<image_text>([^}]|}[^}])*))?}}")
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
        self.code_close_re = re.compile(r"^\}\}\}\s*$", re.U)
        self.macro_close_re = re.compile(r"^>>\s*$", re.U)
        self.conflict_close_re = re.compile(r"^>>>>>>> other\s*$", re.U)
        self.conflict_sep_re = re.compile(r"^=======\s*$", re.U)
        self.display_math_close_re = re.compile(r"^[$][$]\s*$", re.U)
        self.image_re = re.compile(self.image_pat, re.U)
        smileys = r"|".join(re.escape(k) for k in self.smilies)
        smiley_pat = (r"(^|\b|(?<=\s))(?P<smiley_face>%s)"
                      r"((?=[\s.,:;!?)/&=+-])|$)" % smileys)
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
                return ''
            if '#' in addr:
                addr, chunk = addr.split('#', 1)
            if addr == '':
                return ''
            links.append((addr, label))
            return ''
        lines = text.split('\n')
        for part in cls(lines, link, link):
            for ret in links:
                yield ret
            links[:] = []

    def parse(self, enumerated_lines=None):
        """Parse a list of lines of wiki markup, yielding HTML for it."""

        if enumerated_lines is None:
            enumerated_lines = self.enumerated_lines

        def key(enumerated_line):
            line_no, line = enumerated_line
            name, params = self.block_rules.match_one(line)
            return name or "_block_paragraph"

        for kind, block in itertools.groupby(enumerated_lines, key):
            func = getattr(self, kind)

            for part in func(block):
                yield Markup(part)

    def parse_line(self, line):
        """
        Find all the line-level markup and return HTML for it.

        """
        for part in self.markup_rules.parse(line, self):
            yield Markup(part)

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
        return Markup("".join("</%s>" % tag for tag in tags))

    def lines_until(self, close_re):
        """Get lines from input until the closing markup is encountered."""
        try:
            self.line_no, line = next(self.enumerated_lines)
            while not close_re.match(line):
                yield line.rstrip()
                line_no, line = next(self.enumerated_lines)
        except StopIteration:
            pass

# methods for the markup inside lines:

    @markup_rules(r"(?P<table_cell>=?\|=?)", 140)
    def _line_table(self, table_cell):
        return table_cell

    @markup_rules(r"\\\\", 70)
    def _line_linebreak(self):
        return '<br>'

    # Added in .compile()
    def _line_smiley(self, smiley_face):
        try:
            url = self.smilies[smiley_face]
        except KeyError:
            url = ''
        return self.wiki_image(url, smiley_face, class_="smiley")

    @markup_rules(r"[*][*]", 10)
    def _line_bold(self):
        if 'b' in self.stack:
            return self.pop_to('b')
        else:
            self.stack.append('b')
            return Markup("<b>")

    @markup_rules(r"//", 40)
    def _line_italic(self):
        if 'i' in self.stack:
            return self.pop_to('i')
        else:
            self.stack.append('i')
            return Markup("<i>")

    @markup_rules(r"##", 110)
    def _line_mono(self):
        if 'tt' in self.stack:
            return self.pop_to('tt')
        else:
            self.stack.append('tt')
            return Markup("<tt>")

    @markup_rules(r'(?P<punct>'
                  r'(^|\b|(?<=\s))(%s)((?=[\s.,:;!?)/&=+"\'—-])|\b|$))' %
                  r"|".join(re.escape(k) for k in punct), 130)
    def _line_punct(self, punct):
        return self.punct.get(punct, punct)

    @markup_rules(r"\n", 120)
    def _line_newline(self):
        return "\n"

    @markup_rules(r"(?P<plain_text>.+?)", 150)
    def _line_text(self, plain_text):
        return escape(plain_text)

    @markup_rules(r"\$\$(?P<math_text>[^$]+)\$\$", 100)
    def _line_math(self, math_text):
        if self.wiki_math:
            math_text = self.wiki_math(math_text, False)
        else:
            math_text = escape(math_text)
        return tags.var(math_text, class_="inline-math")

    @markup_rules(r"[{][{][{](?P<code_text>([^}]|[^}][}]|[^}][}][}])"
                  r"*[}]*)[}][}][}]", 20)
    def _line_code(self, code_text):
        return '<code>%s</code>' % escape(code_text)

    @markup_rules(r"""(?P<link_url>[a-zA-Z]+://\S+[^\s.,:;!?()'"\*/=+<>-])""", 30)
    def _line_free_link(self, link_url):
        return self._line_link(link_target=link_url)

    @markup_rules(r"""(?P<mail_address>(mailto:)?"""
                  r"""[^\s()\[\]<>{}"']+@\S+(\.[^\s.,:;!?()'"\*/=+<>-]+)+)""" , 90)
    def _line_mail(self, mail_address):
        text = mail_address
        if mail_address.startswith('mailto:'):
            text = text[len('mailto:'):]
        else:
            mail_address = 'mailto:%s' % mail_address
        return self._line_link(link_text=text, link_target=mail_address)

    @markup_rules(r"\[\[(?P<link_target>([^|\]]|\][^|\]])+)"
                  r"(\|(?P<link_text>([^\]]|\][^\]])+))?\]\]", 50)
    def _line_link(self, link_target, link_text=None):
        if not link_text:
            link_text = link_target
            if '#' in link_text:
                link_text, chunk = link_text.split('#', 1)
        match = self.image_re.match(link_text)
        if match:
            params = dict((str(k), v) for (k, v) in
                          match.groupdict().items())
            image = self._line_image(**params)
            return self.wiki_link(link_target, link_text, image=image)
        return self.wiki_link(link_target, link_text)

    @markup_rules(image_pat, 60)
    def _line_image(self, image_target, image_text=None):
        if image_text is None:
            image_text = image_target
        return self.wiki_image(image_target, image_text)

    @markup_rules(r"[<][<](?P<macro_name>\w+)\s+"
                  r"(?P<macro_text>([^>]|[^>][>])+)[>][>]", 80)
    def _line_macro(self, macro_name, macro_text):
        macro_text = macro_text.strip()
        return '<span class="%s">%s</span>' % (
            escape(macro_name),
            escape(macro_text))

# methods for the block (multiline) markup:

    @block_rules(r"^[$][$]\s*$", 25)
    def _block_display_math(self, block):
        for self.line_no, part in block:
            math_text = "\n".join(self.lines_until(self.display_math_close_re))
            if self.wiki_math:
                math_text = self.wiki_math(math_text, True)
            else:
                math_text = escape(math_text)
            yield tags.div(
                math_text,
                class_="display-math",
                id="line_%d" % self.line_no,
            )

    @block_rules(r"^[{][{][{]+\s*$", 20)
    def _block_code(self, block):
        for self.line_no, part in block:
            inside = "\n".join(self.lines_until(self.code_close_re))
            yield tags.pre(Markup(inside), class_="code",
                                    id="line_%d" % self.line_no)

    @block_rules(r"^\{\{\{\#![\w+#.-]+\s*$", 100)
    def _block_syntax(self, block):
        for self.line_no, part in block:
            syntax = part.lstrip('{#!').strip()
            inside = "\n".join(self.lines_until(self.code_close_re))
            if self.wiki_syntax:
                return self.wiki_syntax(inside, syntax=syntax,
                                        line_no=self.line_no)
            else:
                return [tags.div(tags.pre(
                    Markup(inside), id="line_%d" % self.line_no),
                    class_="highlight")]

    @block_rules(r"^<<\w+\s*$", 70)
    def _block_macro(self, block):
        for self.line_no, part in block:
            name = part.lstrip('<').strip()
            inside = "\n".join(self.lines_until(self.macro_close_re))
            yield '<div class="%s">%s</div>' % (
                escape(name),
                escape(inside))

    def _block_paragraph(self, block):
        first_line = None
        para = tags.p()
        for self.line_no, part in block:
            if first_line is None:
                first_line = self.line_no
            para.children.append("".join(self.parse_line(part)))
        para.set_attribute("id", "line_%d" % first_line)
        self.pop_to("")
        yield para

    @block_rules(r"^[ \t]+", 60)
    def _block_indent(self, block):
        parts = []
        first_line = None
        for self.line_no, part in block:
            if first_line is None:
                first_line = self.line_no
            parts.append(part.rstrip())
        text = "\n".join(parts)
        yield tags.pre(Markup(text), id="line_%d" % first_line)

    @block_rules(r"^\|", 110)
    def _block_table(self, block):
        first_line = None
        in_head = False
        for self.line_no, line in block:
            if first_line is None:
                first_line = self.line_no
                yield '<table id="line_%d">' % first_line
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
        yield '</table>'

    @block_rules(r"^\s*$", 40)
    def _block_empty(self, block):
        yield ''

    @block_rules(r"^\s*---+\s*$", 90)
    def _block_rule(self, block):
        for self.line_no, line in block:
            yield tags.hr()

    @block_rules(heading_pat, 50)
    def _block_heading(self, block):
        for self.line_no, line in block:
            level = min(len(self.heading_re.match(line).group(0).strip()), 5)
            self.headings[level - 1] = self.headings.get(level - 1, 0) + 1
            label = "-".join(str(self.headings.get(i, 0))
                              for i in range(level))
            yield tags.a(name="head-%s" % label)
            yield '<h%d id="line_%d">%s</h%d>' % (level, self.line_no,
                escape(line.strip("= \t\n\r\v")), level)

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
            yield '<li>%s%s' % ("".join(self.parse_line(content)),
                                self.pop_to(""))
            in_ul = False
        yield ('</li></%s>' % kind) * level

    @block_rules(quote_pat, 80)
    def _block_quote(self, block):
        yield '<blockquote>'

        def remove_lead(enumerated_line):
            line_no, line = enumerated_line
            stripped = line.lstrip()[1:].lstrip()
            return (line_no, stripped)

        enumerated_lines = list(map(remove_lead, block))
        for content in self.parse(enumerated_lines):
            yield content

        yield '</blockquote>'

    @block_rules(r"^<<<<<<< local\s*$", 30)
    def _block_conflict(self, block):
        for self.line_no, part in block:
            yield '<div class="conflict">'
            local = "\n".join(self.lines_until(self.conflict_sep_re))
            yield tags.pre(Markup(local),
                                    class_="local",
                                    id="line_%d" % self.line_no)
            other = "\n".join(self.lines_until(self.conflict_close_re))
            yield tags.pre(Markup(other),
                                    class_="other",
                                    id="line_%d" % self.line_no)
            yield '</div>'


class WikiWikiParser(WikiParser):
    """A version of WikiParser that recognizes WikiWord links."""

    markup_rules = RuleSet(WikiParser.markup_rules)

    camel_link = r"\w+[%s]\w+" % re.escape(
        ''.join(chr(i) for i in range(sys.maxunicode)
        if unicodedata.category(chr(i)) == 'Lu'))

    @markup_rules(r'(?P<camel_link>%s)' % camel_link, 105)
    def _line_camel_link(self, camel_link):
        return self._line_link(link_target=camel_link)

    @markup_rules(r"[!~](?P<camel_text>%s)" % camel_link, 106)
    def _line_camel_nolink(self, camel_text):
        return escape(camel_text)
