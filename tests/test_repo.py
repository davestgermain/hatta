#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
This is a set of unit tests for testing the repository storage of Hatta wiki
engine. To run it, run py.test (at least version 1.0) from the main Hatta
directory.
"""

import os
import sys

import hatta
import py
import werkzeug

# Patch for no gettext
hatta._ = lambda x:x

def clear_directory(top):
    """
    A helper function to remove a directory with all its contents.
    """

    for root, dirs, files in os.walk(top, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            path = os.path.join(root, name)
            if os.path.islink(path):
                os.remove(path)
            else:
                os.rmdir(path)
    try:
        os.removedirs(top)
    except OSError:
        pass

def pytest_funcarg__repo(request):
    """
    This function is executed whenever a test needs a "repo" parameter.
    It creates a new WikiStorage object with Hatta repository in a
    temporary directory.
    """

    repo_path = str(request.config.ensuretemp('repo'))
    request.addfinalizer(lambda: clear_directory(repo_path))
    return hatta.WikiStorage(repo_path)

class TestMercurialStorage(object):
    """
    Groups tests specific to Hatta's default storage.
    """

    title = 'test title'
    filename = 'test%20title'
    author = u'test author'
    text = u'test text'
    comment = u'test comment'

    def test_filename(self, repo):
        """
        Check if the page's file is named properly.
        """

        title = u'../some/+s page/ąęść?.txt'
        filename = '..%2Fsome%2F%2Bs%20page%2F%C4%85%C4%99%C5%9B%C4%87%3F.txt'
        filepath = os.path.join(repo.path, filename)
        repo.save_text(title, self.text, self.author, self.comment, parent=-1)
        assert os.path.exists(filepath)

    def test_symlinks(self, repo):
        """
        Make sure access to symlinks is blocked.
        """

        path = os.path.join(repo.path, self.filename)
        os.symlink('/', path)
        py.test.raises(werkzeug.exceptions.Forbidden, repo.save_text,
                       self.title, self.text, self.author, self.comment,
                       parent=-1)
        py.test.raises(werkzeug.exceptions.Forbidden, repo.open_page,
                       self.title)

    def test_symlinks_not_exist(self, repo):
        """
        Make sure symlinks are not reported as existing pages.
        """

        path = os.path.join(repo.path, self.filename)
        os.symlink('/', path)
        assert self.title not in repo

    def test_directories_not_exist(self, repo):
        """
        Make sure direcotries are not reported as existing pages.
        """

        path = os.path.join(repo.path, self.filename)
        os.mkdir(path)
        assert self.title not in repo

class TestStorage(object):
    """
    This class groups the general tests for Hatta storage that should
    always pass, no matter what configuration is used.
    """

    text = u"test text"
    title = u"test title"
    author = u"test author"
    comment = u"test comment"

    def test_save_text(self, repo):
        """
        Create a page and read its contents, verify that it matches.
        """

        repo.save_text(self.title, self.text, self.author, self.comment,
                       parent=-1)
        saved = repo.open_page(self.title).read()
        assert saved == self.text

    def test_save_text_noparent(self, repo):
        """
        Save a page with parent set to None.
        """

        repo.save_text(self.title, self.text, self.author, self.comment,
                       parent=None)
        saved = repo.open_page(self.title).read()
        assert saved == self.text

    def test_save_merge_no_conflict(self, repo):
        """
        Create a page two times, with the same content. Verify that
        it is merged correctly.
        """

        text = u"test\ntext"
        repo.save_text(self.title, text, self.author, self.comment, parent=-1)
        repo.save_text(self.title, text, self.author, self.comment, parent=-1)
        saved = repo.open_page(self.title).read()
        assert saved == text

    def test_save_merge_line_conflict(self, repo):
        """
        Modify a page twice, saving conflicting content. Verify that merge
        markers are inserted properly.
        """

        text = u"""\
123
456
789"""
        text1 = u"""\
123
000
789"""
        text2 = u"""\
123
111
789"""
        repo.save_text(self.title, text, self.author, self.comment, parent=-1)
        repo.save_text(self.title, text1, self.author, self.comment, parent=0)
        repo.save_text(self.title, text2, self.author, self.comment, parent=0)
        saved = repo.open_page(self.title).read()
        assert saved == u"""\
123
<<<<<<< local
111
=======
000
>>>>>>> other
789"""

    def test_delete(self, repo):
        """
        Create and delete a page.
        """

        repo.save_text(self.title, self.text, self.author, self.comment,
                       parent=-1)
        assert self.title in repo
        repo.delete_page(self.title, self.author, self.comment)
        assert self.title not in repo


    def test_metadata(self, repo):
        """
        Test that metadata is created and retrieved properly.
        """

        repo.save_text(self.title, self.text, self.author, self.comment,
                       parent=-1)
        rev, date, author, comment = repo.page_meta(self.title)
        assert rev == 0
        assert author == self.author
        assert comment == self.comment

