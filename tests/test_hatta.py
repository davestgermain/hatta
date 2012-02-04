#!/usr/bin/python
# -*- coding: utf-8 -*-

import hatta
import werkzeug
import os
import py.test
import lxml.doctestcompare
from test_parser import HTML

def clear_directory(top):
    for root, dirs, files in os.walk(top, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    try:
        os.removedirs(top)
    except OSError:
        pass

def pytest_funcarg__wiki(request):
    basedir = str(request.config.ensuretemp('repo'))
    config = hatta.WikiConfig(
        pages_path=os.path.join(basedir, 'pages'),
        cache_path=os.path.join(basedir, 'cache'),
    )
    request.addfinalizer(lambda: clear_directory(basedir))
    return hatta.Wiki(config)


class TestHattaStandalone(object):
    docstring = '''<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
"http://www.w3.org/TR/html4/strict.dtd">'''


    def test_japanese_splitting(self, wiki):
        text = u"ルビハイパンツアクセシウェブ内容アテストスイトどらプロセスドクリック」インタラクションディア,情報セットセシビリティングシステムをマその他リア式会を始めてみようサイトをアクセシブ内准剛のな,健二仕ルビの再形式化セシビリテのためらすかるコンテンウェブ内容アネッユザエクアップテキストマでの,ネックセスふべからずビリティにるその他クアップコンテンツアクセネッ"
        after = [u'ルビハイパンツアクセシウェブ', u'内容', u'アテストスイト', u'どら', u'プロセスドクリック', u'インタラクションディア', u'情報', u'セットセシビリティングシステム', u'を', u'マ', u'その', u'他', u'リア', u'式会', u'を', u'始', u'めてみよう', u'サイト', u'を', u'アクセシブ', u'内准剛', u'のな', u'健二仕', u'ルビ', u'の', u'再形式化', u'セシビリテ', u'のためらすかる', u'コンテンウェブ', u'内容', u'アネッユザエクアップテキストマ', u'での', u'ネックセス', u'ふべからず', u'ビリティ', u'にるその', u'他', u'クアップコンテンツアクセネッ']
        result = list(wiki.index.split_japanese_text(text))
        for got, expected in zip(result, after):
            assert got == expected

    def test_front_page(self, wiki):
        """Check that Home page doesn't exist and redirects to editor."""

        client = werkzeug.Client(wiki.application, hatta.WikiResponse)
        response = client.get('')
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
        response = client.get('')
        assert response.status_code == 200

    def test_page_docstring(self, wiki):
        """Check the page's docstring."""

        client = werkzeug.Client(wiki.application, hatta.WikiResponse)
        data = 'text=test&parent=-1&comment=created&author=test&save=Save'
        response = client.post('/+edit/Home', data=data,
                            content_type='application/x-www-form-urlencoded')
        assert response.status_code == 303
        response = client.get('')
        assert response.status_code == 200
        data = ''.join(response.data)
        assert data.startswith(self.docstring)

    def test_editor_docstring(self, wiki):
        """Check the editor's docstring."""

        client = werkzeug.Client(wiki.application, hatta.WikiResponse)
        response = client.get('/+edit/Home')
        data = ''.join(response.data)
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
        response = client.get('/+search?q=test')
        assert response.status_code == 200
        data = ''.join(response.data)
        assert '>searching</a>' in data

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
            return u"<a></a>"
        def image(addr, label=None, class_=None, image=None, alt=None):
            return u"<img>"
        return u''.join(parser(text.split('\n'), link, image))


    test_cases = {
u"""hello world""": u"""<p id="line_0">hello world</p>""",
#--------------------------------------------------------------------
u"""{{{
some code
more
}}}
some text
{{{
more code
}}}""": u"""<pre class="code" id="line_1">some code
more</pre><p id="line_4">some text</p><pre class="code" id="line_6">more code</pre>""",
#--------------------------------------------------------------------
u"""{{{#!python
some code
more
}}}
some text
{{{#!bash
more code
}}}""": u"""<div class="highlight"><pre id="line_1">some code
more</pre></div><p id="line_4">some text</p><div class="highlight"><pre id="line_6">more code</pre></div>""",
#--------------------------------------------------------------------
u"""Here's a quote:
> Here is
> another //quote//:
>> A quote **within
>> a quote
normal text""": u"""<p id="line_0">Here's a quote:</p><blockquote><p id="line_1">Here is
another <i>quote</i>:</p><blockquote><p id="line_3">A quote <b>within
a quote</b></p></blockquote></blockquote><p id="line_5">normal text</p>""",
#--------------------------------------------------------------------
u"""* sample list
** sublist
*** sub-sub-list with **bold
* list""": u"""<ul id="line_0"><li>sample list<ul id="line_1"><li>sublist<ul id="line_2"><li>sub-sub-list with <b>bold</b></li></ul></li></ul></li><li>list</li></ul>""",
}

    def test_test_cases(self):
        for text, expect in self.test_cases.iteritems():
            assert expect == self.parse_text(text)


def pytest_funcarg__req(request):
    basedir = str(request.config.ensuretemp('repo'))
    request.addfinalizer(lambda: clear_directory(basedir))
    config = hatta.WikiConfig(
        pages_path=os.path.join(basedir, 'pages'),
        cache_path=os.path.join(basedir, 'cache'),
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
        assert request.get_url('title') == u'/title'
        assert request.get_download_url('title') in (
            u'/+download/title',
            u'/%2Bdownload/title',
        )
        assert request.get_url('title', wiki.edit) in (
            u'/+edit/title',
            u'/%2Bedit/title',
        )
        assert request.get_url(None, wiki.favicon_ico) == u'/favicon.ico'

    @py.test.mark.xfail
    def test_html_page(self, req):
        wiki, request = req
        content = ["some &lt;content&gt;"]
        title = "page <title>"
        page = wiki.get_page(request, title)
        parts = page.render_content(content)
        html = HTML(u"".join(parts))
        assert html == u"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
"http://www.w3.org/TR/html4/strict.dtd">
<html><head>
    <title>page &lt;title&gt; - Hatta Wiki</title>
    <link type="text/css" href="/+download/pygments.css" rel="stylesheet">
    <link type="text/css" href="/+download/style.css" rel="stylesheet">
    <link type="application/wiki" href="/+edit/page%20%3Ctitle%3E" rel="alternate">
    <link type="image/x-icon" href="/favicon.ico" rel="shortcut icon">
    <link type="application/rss+xml" href="/+feed/atom" rel="alternate" title="Hatta Wiki (ATOM)">
    <script src="/+download/scripts.js" type="text/javascript"></script>
</head><body>
    <div class="header">
        <form action="/+search" class="search" method="GET"><div>
            <input class="search" name="q">
            <input class="button" type="submit" value="Search">
        </div></form>
        <div class="menu">
          <a href="/Home" title="Home" class="wiki nonexistent">Home</a>
          <a href="/+history" title="+history" class="special">Recent changes</a>
        </div>
        <h1>page &lt;title&gt;</h1>
    </div>
    <div class="content">some &lt;content&gt;
    <div class="footer">
        <a href="/+edit/page%20%3Ctitle%3E" class="edit">Edit</a>
        <a href="/+history/page%20%3Ctitle%3E" class="history">History</a>
        <a href="/+search/page%20%3Ctitle%3E" class="backlinks">Backlinks</a>
    </div></div>
</body></html>"""

        page_title = "different <title>"
        page = wiki.get_page(request, title)
        parts = page.render_content(content, page_title)
        html = HTML(u"".join(parts))
        assert html == u"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
"http://www.w3.org/TR/html4/strict.dtd">
<html><head>
    <title>different &lt;title&gt; - Hatta Wiki</title>
    <link type="text/css" href="/+download/pygments.css" rel="stylesheet">
    <link type="text/css" href="/+download/style.css" rel="stylesheet">
    <meta content="NOINDEX,NOFOLLOW" name="robots">
    <link type="image/x-icon" href="/favicon.ico" rel="shortcut icon">
    <link type="application/rss+xml" href="/+feed/atom" rel="alternate" title="Hatta Wiki (ATOM)">
    <script src="/+download/scripts.js" type="text/javascript"></script>
</head><body>
    <div class="header">
        <form action="/+search" class="search" method="GET"><div>
            <input class="search" name="q">
            <input class="button" type="submit" value="Search">
        </div></form>
        <div class="menu">
          <a href="/Home" title="Home" class="wiki nonexistent">Home</a>
          <a href="/+history" title="+history" class="special">Recent changes</a>
        </div>
        <h1>different &lt;title&gt;</h1>
    </div>
    <div class="content">some &lt;content&gt;
       </div>
</body></html>"""


