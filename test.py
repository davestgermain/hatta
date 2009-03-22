#!/usr/bin/python
# -*- coding: utf-8 -*-

import hatta
import unittest
import werkzeug
import os
import lxml.doctestcompare

def clear_directory(top):
    for root, dirs, files in os.walk(top, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.removedirs(top)

class HattaStandalone(unittest.TestCase):
    docstring = '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">'
    basedir = '/tmp/hatta-test'

    def setUp(self):
        self.config = hatta.WikiConfig(
            pages_path=os.path.join(self.basedir, 'pages'),
            cache_path=os.path.join(self.basedir, 'cache'),
        )
        self.wiki = hatta.Wiki(self.config)
        self.app = self.wiki.application
        self.client = werkzeug.Client(self.app, hatta.WikiResponse)

    def tearDown(self):
        clear_directory(self.basedir)

    def test_front_page(self):
        """Check that Home page doesn't exist and redirects to editor."""

        response = self.client.get('')
        self.assertEqual(response.status_code, 303)
        response = self.client.get('/edit/Home')
        self.assertEqual(response.status_code, 404)

    def test_create_front_page(self):
        """Create a Home page and make sure it's created propely."""

        data = 'text=test&parent=-1&comment=created&author=test&save=Save'
        response = self.client.post('/edit/Home', data=data, content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 303)
        response = self.client.get('')
        self.assertEqual(response.status_code, 200)

    def test_page_docstring(self):
        """Check the page's docstring."""

        data = 'text=test&parent=-1&comment=created&author=test&save=Save'
        response = self.client.post('/edit/Home', data=data,
                            content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 303)
        response = self.client.get('')
        self.assertEqual(response.status_code, 200)
        data = ''.join(response.data)
        self.assert_(data.startswith(self.docstring))

    def test_editor_docstring(self):
        """Check the editor's docstring."""

        response = self.client.get('/edit/Home')
        data = ''.join(response.data)
        self.assert_(data.startswith(self.docstring))

    def test_create_slash_page(self):
        """Create a page with slash in name."""

        data = 'text=test&parent=-1&comment=created&author=test&save=Save'
        response = self.client.post('/edit/1/2', data=data,
                            content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 303)
        response = self.client.get('/1/2')
        self.assertEqual(response.status_code, 200)
        response = self.client.get('/history/1/2/0')
        self.assertEqual(response.status_code, 200)

    def test_search(self):
        """Test simple searching."""

        data = 'text=test&parent=-1&comment=created&author=test&save=Save'
        response = self.client.post('/edit/searching', data=data,
                            content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 303)
        response = self.client.get('/search?q=test')
        self.assertEqual(response.status_code, 200)
        data = ''.join(response.data)
        self.assert_('>searching</a>' in data)

    def test_read_only_edit(self):
        self.config.read_only = True
        data = 'text=test&parent=-1&comment=created&author=test&save=Save'
        response = self.client.post('/edit/readonly', data=data,
                            content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 403)

    def test_read_only_undo(self):
        self.config.read_only = True
        data = '52=Undo'
        response = self.client.post('/undo/readonly', data=data,
                            content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 403)



class HattaParser(unittest.TestCase):

    def parse_text(self, text):
        parser = hatta.WikiParser
        def link(addr, label=None, class_=None, image=None, alt=None):
            return u"<a></a>"
        def image(addr, label=None, class_=None, image=None, alt=None):
            return u"<img>"
        return u''.join(parser(text.split('\n'), link, image))


    test_cases = {
u"""hello world""": u"""<p>hello world</p>""",
#--------------------------------------------------------------------
u"""{{{
some code
more
}}}
some text
{{{
more code
}}}""": u"""<pre class="code">some code
more</pre><p>some text</p><pre class="code">more code</pre>""",
#--------------------------------------------------------------------
u"""{{{#!python
some code
more
}}}
some text
{{{#!bash
more code
}}}""": u"""<div class="highlight"><pre>some code
more</pre></div><p>some text</p><div class="highlight"><pre>more code</pre></div>""",
#--------------------------------------------------------------------
u"""Here's a quote:
> Here is
> another //quote//:
>> A quote **within
>> a quote
normal text""": u"""<p>Here's a quote:</p><blockquote><p>Here is
another <i>quote</i>:</p><blockquote><p>A quote <b>within
a quote</b></p></blockquote></blockquote><p>normal text</p>""",
#--------------------------------------------------------------------
u"""* sample list
** sublist
*** sub-sub-list with **bold
* list""": u"""<ul><li>sample list<ul><li>sublist<ul><li>sub-sub-list with <b>bold</b></li></ul></li></ul><li>list</li></ul>""",
}

    def test_test_cases(self):
        for text, expect in self.test_cases.iteritems():
            self.assertEqual(expect, self.parse_text(text))

class Example(object):
    def __init__(self, want):
        self.want = want

class TestHTML(unittest.TestCase):
    basedir = '/tmp/hatta-test'
    checker = lxml.doctestcompare.LHTMLOutputChecker()

    def html_eq(self, want, got):
        if not self.checker.check_output(want, got, 0):
            raise Exception(self.checker.output_difference(Example(want), got, 0))

    def setUp(self):
        self.config = hatta.WikiConfig(
            pages_path=os.path.join(self.basedir, 'pages'),
            cache_path=os.path.join(self.basedir, 'cache'),
        )
        self.config.default_style = "..."
        self.wiki = hatta.Wiki(self.config)
        environ = {
            'SERVER_NAME': 'hatta',
            'wsgi.url_scheme': 'http',
            'SERVER_PORT': '80',
            'REQUEST_METHOD': 'GET',
            'PATH_INFO': '/',
            'SCRIPT_NAME': '',
        }
        adapter = self.wiki.url_map.bind_to_environ(environ)
        self.request = hatta.WikiRequest(self.wiki, adapter, environ)

    def tearDown(self):
        clear_directory(self.basedir)

    def test_wiki_request_get_url(self):
        self.assertEqual(self.request.get_url('title'),
                         u'/title')
        self.assertEqual(self.request.get_download_url('title'),
                         u'/download/title')
        self.assertEqual(self.request.get_url('title', self.wiki.edit),
                         u'/edit/title')
        self.assertEqual(self.request.get_url(None, self.wiki.favicon),
                         u'/favicon.ico')


    def test_html_page(self):
        content = ["some &lt;content&gt;"]
        title = "page <title>"
        page = hatta.WikiPage(self.wiki, self.request, title)
        parts = page.render_content(content)
        html = u"".join(parts)
        expect = u"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
"http://www.w3.org/TR/html4/strict.dtd">
<html><head>
    <title>page &lt;title&gt; - Hatta Wiki</title>
    <style type="text/css">...</style>
    <link type="application/wiki" href="/edit/page%20%3Ctitle%3E" rel="alternate">
    <link type="image/x-icon" href="/favicon.ico" rel="shortcut icon">
    <link type="application/rss+xml" href="/feed/rss" rel="alternate" title="Hatta Wiki (RSS)">
    <link type="application/rss+xml" href="/feed/atom" rel="alternate" title="Hatta Wiki (ATOM)">
</head><body>
    <div class="header">
        <form action="/search" class="search" method="GET"><div>
            <input class="search" name="q">
            <input class="button" type="submit" value="Search">
        </div></form>
        <h1>page &lt;title&gt;</h1>
    </div>
    <div class="content">some &lt;content&gt;
    <div class="footer">
        <a href="/edit/page%20%3Ctitle%3E" class="edit">Edit</a>
        <a href="/history/page%20%3Ctitle%3E" class="history">History</a>
        <a href="/search/page%20%3Ctitle%3E" class="backlinks">Backlinks</a>
    </div></div>
</body></html>"""
        self.html_eq(expect, html)
        page_title = "different <title>"
        page = hatta.WikiPage(self.wiki, self.request, title)
        parts = page.render_content(content, page_title)
        html = u"".join(parts)
        expect = u"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
"http://www.w3.org/TR/html4/strict.dtd">
<html><head>
    <title>different &lt;title&gt; - Hatta Wiki</title>
    <style type="text/css">...</style>
    <meta content="NOINDEX,NOFOLLOW" name="robots">
    <link type="image/x-icon" href="/favicon.ico" rel="shortcut icon">
    <link type="application/rss+xml" href="/feed/rss" rel="alternate" title="Hatta Wiki (RSS)">
    <link type="application/rss+xml" href="/feed/atom" rel="alternate" title="Hatta Wiki (ATOM)">
</head><body>
    <div class="header">
        <form action="/search" class="search" method="GET"><div>
            <input class="search" name="q">
            <input class="button" type="submit" value="Search">
        </div></form>
        <h1>different &lt;title&gt;</h1>
    </div>
    <div class="content">some &lt;content&gt;</div>
</body></html>"""
        self.html_eq(expect, html)

if __name__ == '__main__':
    unittest.main()

