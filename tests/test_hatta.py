#!/usr/bin/python
# -*- coding: utf-8 -*-

import werkzeug
import os
import time
import pytest
import lxml.doctestcompare
from .test_parser import HTML

import hatta


def clear_directory(top):
    time.sleep(.25)
    for root, dirs, files in os.walk(top, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    try:
        os.removedirs(top)
    except OSError:
        pass


@pytest.fixture
def wiki(request, tmp_path):
    config = hatta.WikiConfig(
        pages_path=os.path.join(tmp_path, 'pages'),
        cache_path=os.path.join(tmp_path, 'cache'),
    )
    request.addfinalizer(lambda: clear_directory(tmp_path))
    return hatta.Wiki(config)


class TestHattaStandalone(object):
    docstring = b'''<!doctype html>\n<html lang="en">'''


    def test_japanese_splitting(self, wiki):
        text = "ルビハイパンツアクセシウェブ内容アテストスイトどらプロセスドクリック」インタラクションディア,情報セットセシビリティングシステムをマその他リア式会を始めてみようサイトをアクセシブ内准剛のな,健二仕ルビの再形式化セシビリテのためらすかるコンテンウェブ内容アネッユザエクアップテキストマでの,ネックセスふべからずビリティにるその他クアップコンテンツアクセネッ"
        after = ['ルビハイパンツアクセシウェブ', '内容', 'アテストスイト', 'どら', 'プロセスドクリック', 'インタラクションディア', '情報', 'セットセシビリティングシステム', 'を', 'マ', 'その', '他', 'リア', '式会', 'を', '始', 'めてみよう', 'サイト', 'を', 'アクセシブ', '内准剛', 'のな', '健二仕', 'ルビ', 'の', '再形式化', 'セシビリテ', 'のためらすかる', 'コンテンウェブ', '内容', 'アネッユザエクアップテキストマ', 'での', 'ネックセス', 'ふべからず', 'ビリティ', 'にるその', '他', 'クアップコンテンツアクセネッ']
        result = list(wiki.index.split_japanese_text(text))
        for got, expected in zip(result, after):
            assert got == expected

    def test_front_page(self, wiki):
        """Check that Home page doesn't exist and redirects to editor."""

        client = werkzeug.Client(wiki.application, hatta.WikiResponse)
        response = client.get('/')
        assert response.status_code == 303
        assert response.headers['Location'] in (
            'http://localhost/+edit/Home',
            'http://localhost/%2Bedit/Home',
        )
        response = client.get('/+edit/Home')
        assert response.status_code == 404

    def test_create_front_page(self, wiki):
        """Create a Home page and make sure it's created propely."""

        client = werkzeug.Client(wiki.application, hatta.WikiResponse)
        data = 'text=test&parent=-1&comment=created&author=test&save=Save'
        response = client.post('/+edit/Home', data=data, content_type='application/x-www-form-urlencoded')
        assert response.status_code == 303
        response = client.get('/')
        assert response.status_code == 200

    def test_page_docstring(self, wiki):
        """Check the page's docstring."""

        client = werkzeug.Client(wiki.application, hatta.WikiResponse)
        data = 'text=test&parent=-1&comment=created&author=test&save=Save'
        response = client.post('/+edit/Home', data=data,
                            content_type='application/x-www-form-urlencoded')
        assert response.status_code == 303
        response = client.get('/')
        assert response.status_code == 200
        data = b''.join(response.response)
        assert data.startswith(self.docstring)

    def test_editor_docstring(self, wiki):
        """Check the editor's docstring."""

        client = werkzeug.Client(wiki.application, hatta.WikiResponse)
        response = client.get('/+edit/Home')
        data = b''.join(response.response)
        assert data.startswith(self.docstring)

    def test_create_slash_page(self, wiki):
        """Create a page with slash in name."""

        client = werkzeug.Client(wiki.application, hatta.WikiResponse)
        data = 'text=test&parent=-1&comment=created&author=test&save=Save'
        response = client.post('/+edit/1/2', data=data,
                            content_type='application/x-www-form-urlencoded')
        assert response.status_code == 303
        response = client.get('/1/2')
        assert response.status_code == 200
        response = client.get('/+history/1/2/0')
        assert response.status_code == 200

    def test_search(self, wiki):
        """Test simple searching."""

        client = werkzeug.Client(wiki.application, hatta.WikiResponse)
        data = 'text=test&parent=-1&comment=created&author=test&save=Save'
        response = client.post('/+edit/searching', data=data,
                            content_type='application/x-www-form-urlencoded')
        assert response.status_code == 303
        time.sleep(1)
        response = client.get('/+search?q=test')
        assert response.status_code == 200
        data = b''.join(response.response)
        assert b'>searching</a>' in data

    def test_read_only_edit(self, wiki):
        client = werkzeug.Client(wiki.application, hatta.WikiResponse)
        wiki.read_only = True
        data = 'text=test&parent=-1&comment=created&author=test&save=Save'
        response = client.post('/+edit/readonly', data=data,
                            content_type='application/x-www-form-urlencoded')
        assert response.status_code == 403

    def test_read_only_undo(self, wiki):
        client = werkzeug.Client(wiki.application, hatta.WikiResponse)
        wiki.read_only = True
        data = '52=Undo'
        response = client.post('/+undo/readonly', data=data,
                            content_type='application/x-www-form-urlencoded')
        assert response.status_code == 403


class TestHattaParser(object):

    def parse_text(self, text):
        parser = hatta.parser.WikiParser
        def link(addr, label=None, class_=None, image=None, alt=None):
            return "<a></a>"
        def image(addr, label=None, class_=None, image=None, alt=None):
            return "<img>"
        lines = text.splitlines(True)
        return ''.join(parser(lines, link, image))


    test_cases = {
"""hello world""": """<p id="line_0">hello world</p>""",
#--------------------------------------------------------------------
"""hello
world""": """<p id="line_0">hello
world</p>""",
#--------------------------------------------------------------------
"""{{{
some code
more
}}}
some text
{{{
more code
}}}""": """<pre class="code" id="line_1">some code
more</pre><p id="line_4">some text
</p><pre class="code" id="line_6">more code</pre>""",
#--------------------------------------------------------------------
"""{{{#!python
some code
more
}}}
some text
{{{#!bash
more code
}}}""": """<div class="highlight"><pre id="line_1">some code
more</pre></div><p id="line_4">some text
</p><div class="highlight"><pre id="line_6">more code</pre></div>""",
#--------------------------------------------------------------------
"""Here's a quote:
> Here is
> another //quote//:
>> A quote **within
>> a quote
normal text""": """<p id="line_0">Here's a quote:
</p><blockquote><p id="line_1">Here is
another <i>quote</i>:
</p><blockquote><p id="line_3">A quote <b>within
a quote
</b></p></blockquote></blockquote><p id="line_5">normal text</p>""",
#--------------------------------------------------------------------
"""* sample list
** sublist
*** sub-sub-list with **bold
* list""": """<ul id="line_0"><li>sample list<ul id="line_1"><li>sublist<ul id="line_2"><li>sub-sub-list with <b>bold</b></li></ul></li></ul></li><li>list</li></ul>""",
}

    def test_test_cases(self):
        for text, expect in self.test_cases.items():
            assert expect == self.parse_text(text)


@pytest.fixture
def req(request, tmp_path):
    request.addfinalizer(lambda: clear_directory(tmp_path))
    config = hatta.WikiConfig(
        pages_path=os.path.join(tmp_path, 'pages'),
        cache_path=os.path.join(tmp_path, 'cache'),
        default_style="...",
    )
    wiki = hatta.Wiki(config)
    environ = {
        'SERVER_NAME': 'hatta',
        'wsgi.url_scheme': 'http',
        'SERVER_PORT': '80',
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/',
        'SCRIPT_NAME': '',
    }
    adapter = wiki.url_map.bind_to_environ(environ)
    return wiki, hatta.WikiRequest(wiki, adapter, environ)

class TestHTML(object):
    def test_wiki_request_get_url(self, req):
        wiki, request = req
        assert request.get_url('title') == '/title'
        assert request.get_download_url('title') in (
            '/+download/title',
            '/%2Bdownload/title',
        )
        assert request.get_url('title', 'edit') in (
            '/+edit/title',
            '/%2Bedit/title',
        )
        assert request.get_url(None, 'favicon_ico') == '/favicon.ico'

    @pytest.mark.xfail
    def test_html_page(self, req):
        wiki, request = req
        content = ["some &lt;content&gt;"]
        title = "page <title>"
        page = hatta.page.get_page(request, title)
        parts = page.view_content(content)
        rendered = page.template("page.html", content=parts)
        html = HTML("".join(rendered))
        assert html == """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
"http://www.w3.org/TR/html4/strict.dtd">
<html><head>
    <meta content="text/html;charset=utf-8" http-equiv="content-type">
    <title>page &lt;title&gt; - Hatta Wiki</title>
    <link type="text/css" href="/%2Bdownload/style.css" rel="stylesheet">
    <link type="text/css" href="/%2Bdownload/pygments.css" rel="stylesheet">
    <link type="image/x-icon" href="/favicon.ico" rel="shortcut icon">
    <link type="application/rss+xml" href="/%2Bfeed/rss" rel="alternate" title="Hatta Wiki (ATOM)">
    <link type="application/wiki" href="/%2Bedit/page%20%3Ctitle%3E" rel="alternate">
</head><body>
    <div id="hatta-header">
        <form action="/%2Bsearch" id="hatta-search" method="GET"><div>
            <input id="hatta-search-q" name="q">
            <input class="button" type="submit" value="Search">
        </div></form>
        <div id="hatta-menu">
          <a href="/Home" title="Home" class="wiki nonexistent">Home</a>
          <a href="/+history" title="+history" class="special">Recent changes</a>
        </div>
        <h1>page &lt;title&gt;</h1>
    </div>
    <div id="hatta-content">
         <p id="line_0">some &amp;lt;content&amp;gt;</p>
    </div>
    <div id="hatta-footer">
        <a href="/%2Bedit/page%20%3Ctitle%3E" class="edit">Edit</a>
        <a href="/%2Bhistory/page%20%3Ctitle%3E" class="hatta-history">History</a>
        <a href="/%2Bsearch/page%20%3Ctitle%3E" class="hatta-backlinks">Backlinks</a>
    </div>
    <script src="/%2Bdownload/scripts.js" type="text/javascript"></script>
</body></html>"""

        page_title = "different <title>"
        page = hatta.page.get_page(request, title)
        page.title = page_title
        parts = page.view_content(content)
        rendered = page.template("page.html", content=parts)
        html = HTML("".join(rendered))
        assert html == """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
"http://www.w3.org/TR/html4/strict.dtd">
<html><head>
    <meta content="text/html;charset=utf-8" http-equiv="content-type">
    <title>different &lt;title&gt; - Hatta Wiki</title>
    <link type="text/css" href="/%2Bdownload/style.css" rel="stylesheet">
    <link type="text/css" href="/%2Bdownload/pygments.css" rel="stylesheet">
    <link type="image/x-icon" href="/favicon.ico" rel="shortcut icon">
    <link type="application/rss+xml" href="/%2Bfeed/rss" rel="alternate" title="Hatta Wiki (ATOM)">
    <link type="application/wiki" href="/%2Bedit/different%20%3Ctitle%3E" rel="alternate">
</head><body>
    <div id="hatta-header">
        <form action="/%2Bsearch" id="hatta-search" method="GET"><div>
            <input id="hatta-search-q" name="q">
            <input class="button" type="submit" value="Search">
        </div></form>
        <div id="hatta-menu">
          <a href="/Home" title="Home" class="wiki nonexistent">Home</a>
          <a href="/+history" title="+history" class="special">Recent changes</a>
        </div>
        <h1>different &lt;title&gt;</h1>
    </div>
    <div id="hatta-content">
        <p id="line_0">some &amp;lt;content&amp;gt;</p>
    </div>
    <div id="hatta-footer">
        <a href="/%2Bedit/different%20%3Ctitle%3E" class="edit">Edit</a>
        <a href="/%2Bhistory/different%20%3Ctitle%3E" class="hatta-history">History</a>
        <a href="/%2Bsearch/different%20%3Ctitle%3E" class="hatta-backlinks">Backlinks</a>
    </div>
    <script src="/%2Bdownload/scripts.js" type="text/javascript"></script>
</body></html>"""


