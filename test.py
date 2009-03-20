#!/usr/bin/python
# -*- coding: utf-8 -*-

import hatta
import unittest
import werkzeug
import os

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

class TestHTML(unittest.TestCase):
    basedir = '/tmp/hatta-test'

    def setUp(self):
        self.config = hatta.WikiConfig(
            pages_path=os.path.join(self.basedir, 'pages'),
            cache_path=os.path.join(self.basedir, 'cache'),
        )
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

    def test_wiki_request_get_page_url(self):
        self.assertEqual(self.request.get_page_url('title'),
                         u'/title')
        self.assertEqual(self.request.get_download_url('title'),
                         u'/download/title')
        self.assertEqual(self.request.get_page_url('title', self.wiki.edit),
                         u'/edit/title')
        self.assertEqual(self.request.get_page_url(None, self.wiki.favicon),
                         u'/favicon.ico')


    def test_html_page(self):
        content = ["some <content>"]
        title = "page <title>"
        parts = self.wiki.html_page(self.request, title, content)
        html = u"".join(parts)
        self.assertEqual(html, u"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd"><html><head><title>page &lt;title&gt; - Hatta Wiki</title><style type="text/css">html { background: #fff; color: #2e3436;
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
     border-bottom: 1px solid #babdb6; clear: both }
blockquote { border-left:.25em solid #ccc; padding-left:.5em; margin-left:0}</style><link rel="alternate" type="application/wiki" href="/edit/page%20%3Ctitle%3E"><link rel="shortcut icon" type="image/x-icon" href="/favicon.ico"><link rel="alternate" type="application/rss+xml" title="Hatta Wiki (RSS)" href="/feed/rss"><link rel="alternate" type="application/rss+xml" title="Hatta Wiki (ATOM)" href="/feed/atom"></head><body><div class="header"><form class="search" action="/search" method="GET"><div><input name="q" class="search"><input class="button" type="submit" value="Search"></div></form><h1>page &lt;title&gt;</h1></div><div class="content">some <content><div class="footer"><a href="/edit/page%20%3Ctitle%3E" class="edit">Edit</a> <a href="/history/page%20%3Ctitle%3E" class="history">History</a> <a href="/search/page%20%3Ctitle%3E" class="backlinks">Backlinks</a> </div></div></body></html>""")
        page_title = "different <title>"
        parts = self.wiki.html_page(self.request, title, content, page_title)
        html = u"".join(parts)
        self.assertEqual(html, u"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd"><html><head><title>different &lt;title&gt; - Hatta Wiki</title><style type="text/css">html { background: #fff; color: #2e3436;
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
     border-bottom: 1px solid #babdb6; clear: both }
blockquote { border-left:.25em solid #ccc; padding-left:.5em; margin-left:0}</style><meta name="robots" content="NOINDEX,NOFOLLOW"><link rel="shortcut icon" type="image/x-icon" href="/favicon.ico"><link rel="alternate" type="application/rss+xml" title="Hatta Wiki (RSS)" href="/feed/rss"><link rel="alternate" type="application/rss+xml" title="Hatta Wiki (ATOM)" href="/feed/atom"></head><body><div class="header"><form class="search" action="/search" method="GET"><div><input name="q" class="search"><input class="button" type="submit" value="Search"></div></form><h1>different &lt;title&gt;</h1></div><div class="content">some <content></div></body></html>""")

if __name__ == '__main__':
    unittest.main()

