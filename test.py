#!/usr/bin/python
# -*- coding: utf-8 -*-

import hatta
import unittest
import werkzeug
import os


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

    def clear_directory(self, top):
        for root, dirs, files in os.walk(top, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.removedirs(top)

    def tearDown(self):
        self.clear_directory(self.basedir)

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

if __name__ == '__main__':
    unittest.main()

