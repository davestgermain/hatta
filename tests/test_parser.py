#!/usr/bin/python
# -*- coding: utf-8 -*-


from lxml.doctestcompare import LHTMLOutputChecker
import doctest
import werkzeug

import hatta


class HTML(object):
    """
    A class wrapping HTML for better comparison and nicer
    error reporting.
    """
    def __init__(self, text):
        self.text = text
        self.example = doctest.Example('', self.text)
        self.checker = LHTMLOutputChecker()
        self.flags = doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS
        self.print_diff = True

    def compare(self, other, expect_eq):
        if isinstance(other, HTML):
            text = other.text
        else:
            text = other
        eq = self.checker.check_output(self.text, text, self.flags)
        if self.print_diff and eq != expect_eq:
            print self.checker.output_difference(self.example, text, self.flags)
        # Only output diff once per HTML object.
        self.print_diff = False
        return eq

    def __eq__(self, other):
        return self.compare(other, True)

    def __ne__(self, other):
        return self.compare(other, False)

    def __str__(self):
        return str(self.text)

    def __unicode__(self):
        return unicode(self.text)

def link(addr, label, class_=None, image=None, lineno=0):
    href = werkzeug.escape(addr, quote=True)
    text = image or werkzeug.escape(label or addr)
    return u'<a href="%s">%s</a>' % (href, text)

def img(addr, label, class_=None, image=None):
    href = werkzeug.escape(addr, quote=True)
    text = image or werkzeug.escape(label or addr, quote=True)
    return u'<img src="%s" alt="%s">' % (href, text)

def hgh(text, mime=None, syntax=None, line_no=0):
    class DummyPage(hatta.page.WikiPageColorText):
        def __init__(self):
            self.request = self
            self.request.print_highlight_styles = None
    return DummyPage().highlight(text, mime, syntax, line_no)

def parse(text):
    lines = '\n\r'.join(text.split('\n')).split('\r')
    return HTML(u''.join(hatta.parser.WikiParser(lines, link, img, hgh)))

def wiki_parse(text):
    lines = '\n\r'.join(text.split('\n')).split('\r')
    return HTML(u''.join(hatta.parser.WikiWikiParser(lines, link, img, hgh)))


class TestParser(object):
    def test_extract_links(self):
        text = """[[one link]] some
text [[another|link]] more
text [[link]]"""
        links = list(hatta.parser.WikiParser.extract_links(text))
        assert links == [
            ('one link', 'one link'),
            ('another', 'link'),
            ('link', 'link'),
        ]

    def test_basic_paragraph(self):
        html = parse(u'ziew')
        assert html == '<p id="line_0">ziew</p>'

    def test_amp(self):
        html = parse(u"d&d")
        assert html == """<p id="line_0">d&amp;d</p>"""

    def test_basic_header(self):
        html = parse(u"= head =")
        assert html == """<a name="head-1"></a><h1 id="line_0">head</h1>"""

    def test_paragraph_newline(self):
        html = parse(u'test\ntest')
        assert html == """<p id="line_0">test
test</p>"""

    def test_two_paragraphs(self):
        html = parse(u'test\n\ntest')
        assert html == """<p id="line_0">test</p><p id="line_2">test</p>"""

    def test_linebreak(self):
        html = parse(u'test\\\\test')
        assert html == """<p id="line_0">test<br>test</p>"""

    def test_separator(self):
        html = parse(u'----')
        assert html == """<hr>"""

    def test_level_two_header(self):
        html = parse(u'==test==')
        assert html == """<a name="head-0-1"></a><h2 id="line_0">test</h2>"""

    def test_unterminated_header(self):
        html = parse(u'== test')
        assert html == """<a name="head-0-1"></a><h2 id="line_0">test</h2>"""

    def test_overterminated_header(self):
        html = parse(u'==test====')
        assert html == """<a name="head-0-1"></a><h2 id="line_0">test</h2>"""

    def test_level_five_header(self):
        html = parse(u'=====test')
        assert html == """<a name="head-0-0-0-0-1"></a><h5 id="line_0">test</h5>"""

    def test_mix_headers_and_paragraphs(self):
        html = parse(u'==test==\ntest\n===test===')
        assert html == """
            <a name="head-0-1"></a>
            <h2 id="line_0">test</h2>
            <p id="line_1">test</p>
            <a name="head-0-1-1"></a>
            <h3 id="line_2">test</h3>
        """

    def test_basic_bulltes(self):
        html = parse(u'test\n* test line one\n * test line two\ntest')
        assert html == """
            <p id="line_0">test</p>
            <ul id="line_1">
                <li>test line one</li>
                <li>test line two</li>
            </ul>
            <p id="line_3">test</p>
        """

    def test_nested_bullets(self):
        html = parse(u'* test line one\n* test line two\n** Nested item')
        assert html == """
            <ul id="line_0">
                <li>test line one</li>
                <li>test line two<ul id="line_2">
                <li>Nested item</li>
            </ul></li>
            </ul>
        """

    def test_basic_numbers(self):
        html = parse(u'test\n# test line one\n # test line two\ntest')
        assert html == """
            <p id="line_0">test</p>
            <ol id="line_1">
                <li>test line one</li>
                <li>test line two</li>
            </ol>
            <p id="line_3">test</p>
        """

    def test_nested_numbers(self):
        html = parse(u'# test line one\n# test line two\n## Nested item')
        assert html == """
            <ol id="line_0">
                <li>test line one</li>
                <li>test line two<ol id="line_2">
                <li>Nested item</li>
            </ol></li>
            </ol>
        """

    def test_very_nested_numbers(self):
        html = parse(u'# 1\n# 2\n## 2.1\n### 2.1.1\n# 3')
        assert html == """
            <ol id="line_0">
                <li>1</li>
                <li>2<ol id="line_2">
                    <li>2.1<ol id="line_3">
                        <li>2.1.1</li>
                    </ol></li>
                </ol></li>
                <li>3</li>
            </ol>
        """

    def test_mixed_numbers_bullets(self):
        html = parse(u'# test line one\n* test line two\n*# Nested item')
        assert html == """
            <ol id="line_0">
                <li>test line one</li>
                <li>test line two<ol id="line_2">
                <li>Nested item</li>
            </ol></li>
            </ol>
        """

    def test_mixed_bullets_numbers(self):
        html = parse(u'* test line one\n# test line two\n*# Nested item')
        assert html == """
            <ul id="line_0">
                <li>test line one</li>
                <li>test line two<ul id="line_2">
                <li>Nested item</li>
            </ul></li>
            </ul>
        """

    def test_basic_emphasis(self):
        html = parse(u'test //test test// test **test test** test')
        assert html == """<p id="line_0">test <i>test test</i> test <b>test test</b> test</p>"""

    def test_nested_emphasis(self):
        html = parse(u'test //test **test// test** test')
        assert html == """<p id="line_0">test <i>test <b>test</b></i> test<b> test</b></p>"""

    def test_unterminated_emphasis(self):
        html = parse(u'**test')
        assert html == """<p id="line_0"><b>test</b></p>"""

    def test_basic_table(self):
        html = parse(u'|x|y|z|\n|a|b|c|\n|d|e|f|\ntest')
        assert html == """
            <table id="line_0">
                <tr>
                    <td>x</td>
                    <td>y</td>
                    <td>z</td>
                </tr>
                <tr>
                    <td>a</td>
                    <td>b</td>
                    <td>c</td>
                </tr>
                <tr>
                    <td>d</td>
                    <td>e</td>
                    <td>f</td>
                </tr>
            </table>
            <p id="line_3">test</p>
        """

    def test_table_with_head(self):
        html = parse(u'|=x|y|=z=|\n|a|b|c|\n|d|e|=f=|')
        assert html == """
            <table id="line_0">
                <thead><tr>
                    <th>x</th>
                    <td>y</td>
                    <th>z</th>
                </tr></thead>
                <tr>
                    <td>a</td>
                    <td>b</td>
                    <td>c</td>
                </tr>
                <tr>
                    <td>d</td>
                    <td>e</td>
                    <th>f</th>
                </tr>
            </table>
        """

    def test_free_url(self):
        html = parse(u'test http://example.com/test test')
        assert html == """
            <p id="line_0">
                test <a href="http://example.com/test">
                    http://example.com/test
                </a> test
            </p>
        """

    def test_free_url_with_commas(self):
        html = parse(u'http://example.com/,test, test')
        assert html == """
            <p id="line_0">
                <a href="http://example.com/,test">http://example.com/,test</a>, test
            </p>
        """

    def test_free_url_with_parens(self):
        html = parse(u'(http://example.com/test)')
        assert html == """
            <p id="line_0">
                (<a href="http://example.com/test">http://example.com/test</a>)
            </p>
        """

        # This might be considered a bug, but impossible to detect in general.
        html = parse(u'http://example.com/(test)')
        assert html == """
            <p id="line_0">
                <a href="http://example.com/(test">http://example.com/(test</a>)
            </p>
        """

    def test_free_url_with_query_string(self):
        html = parse(u'http://example.com/test?test&test=1')
        assert html == """
            <p id="line_0">
                <a href="http://example.com/test?test&amp;test=1"> http://example.com/test?test&amp;test=1
            </a></p>
        """

    def test_free_url_with_tilde(self):
        html = parse(u'http://example.com/~test')
        assert html == """
            <p id="line_0">
                <a href="http://example.com/~test">http://example.com/~test</a>
            </p>
        """

    def test_wiki_link(self):
        html = parse(u'[[test]] [[tset|test]]')
        assert html == """
            <p id="line_0">
                <a href="test">test</a> <a href="tset">test</a>
            </p>
        """

    def test_url_link(self):
        html = parse(u'[[http://example.com|test]]')
        assert html == """
            <p id="line_0">
                <a href="http://example.com">test</a>
            </p>
        """

    def test_pre(self):
        html = parse(u'{{{\nlorem ipsum\n}}}')
        assert html == """<pre id="line_1" class="code">lorem ipsum</pre>"""

    def test_text(self):
        html = parse(u'{{{#!text\nlorem ipsum\n}}}')
        assert html == """<div class="highlight"><pre><span id="line_1">lorem ipsum</span></pre></div>"""

    def test_highlight(self):
        html = parse(u'{{{#!c++\nint eger;\n}}}')
        assert html == """<div class="highlight"><pre><span id="line_1"><span class="kt">int</span> <span class="n">eger</span><span class="p">;</span></span></pre></div>"""

    def test_basic_table(self):
        html = parse(u'|table|')
        assert html == """<table id="line_0"><tr><td>table</td></tr></table>"""

    def test_two_cell_table(self):
        html = parse(u'|table| cell |')
        assert html == """<table id="line_0"><tr><td>table</td><td> cell </td></tr></table>"""

    def test_table_head(self):
        html = parse(u'|table|=head=|')
        assert html == """<table id="line_0"><tr><td>table</td><th>head</th></tr></table>"""

    def test_table_head_row(self):
        html = parse(u'|=table=|=head=|')
        assert html == """<table id="line_0"><thead><tr><th>table</th><th>head</th></tr></thead></table>"""

    def test_table_link(self):
        html = parse(u'|table|[[link|link]]|')
        assert html == """<table id="line_0"><tr><td>table</td><td><a href="link">link</a></td></tr></table>"""

    def test_table_image(self):
        html = parse(u'|table|{{img|img}}|')
        assert html == """<table id="line_0"><tr><td>table</td><td><img src="img" alt="img"></td></tr></table>"""

    def test_table_pre(self):
        html = parse(u'|table|{{{code|code}}}|')
        assert html == """<table id="line_0"><tr><td>table</td><td><code>code|code</code></td></tr></table>"""

    def test_wiki_word(self):
        html = wiki_parse(u'some wikiWord, here')
        assert html == """<p id="line_0">some <a href="wikiWord">wikiWord</a>, here</p>"""

    def test_wiki_word_escape(self):
        html = wiki_parse(u'no !wikiWord here, ~wikiWord')
        assert html == """<p id="line_0">no wikiWord here, wikiWord</p>"""

    def test_emoticon(self):
        html = parse(u'lol:)')
        assert html == """<p id="line_0">lol<img src="smile.png" alt=":)"></p>"""

    def test_monotype(self):
        html = parse(u'This is ##monotyped## text.')
        assert html == """<p id="line_0">This is <tt>monotyped</tt> text.</p>"""

