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
import py.test
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
    return hatta.storage.WikiStorage(repo_path)

def pytest_funcarg__subdir_repo(request):
    """
    This function is executed whenever a test needs a "repo" parameter.
    It creates a new WikiSubdirectoryStorage object with Hatta repository in a
    temporary directory.
    """

    repo_path = str(request.config.ensuretemp('repo'))
    request.addfinalizer(lambda: clear_directory(repo_path))
    return hatta.storage.WikiSubdirectoryStorage(repo_path)

class TestSubdirectoryStorage(object):
    """
    Tests for the WikiSubdirectoryStorage.
    """

    author = u'test author'
    text = u'test text'
    comment = u'test comment'

    title_encodings = {
        u'test title': 'test title',
        u'.test title': '%2Etest title',
        u'../test title': '%2E./test title',
        u'test/./title': 'test/%2E/title',
        u'test/../title': 'test/%2E./title',
        u'test//title': 'test/%2Ftitle',
        u'/test/title': '%2Ftest/title',
    }


    def test_title_to_file(self, subdir_repo):
        """
        Test the modified filename escpaing.
        """

        for title, filename in self.title_encodings.iteritems():
            escaped = subdir_repo._title_to_file(title)
            assert escaped == filename

    def test_filename(self, subdir_repo):
        """
        Check if the page's file is named properly.
        """

        for title, filename in self.title_encodings.iteritems():
            filepath = os.path.join(subdir_repo.path, filename)
            subdir_repo.save_text(title, self.text, self.author, self.comment,
                                  parent=-1)
            exists = os.path.exists(filepath)
            assert exists

    def test_subdirectory_delete(self, subdir_repo):
        """
        Check if empty subdirectories are removed on page delete.
        """

        title = u'foo/bar'
        filepath = os.path.join(subdir_repo.path, 'foo/bar')
        dirpath = os.path.join(subdir_repo.path, 'foo')
        subdir_repo.save_text(title, self.text, self.author, self.comment,
                              parent=-1)
        subdir_repo.delete_page(title, self.author, self.comment)
        exists = os.path.exists(filepath)
        assert not exists
        exists = os.path.exists(dirpath)
        assert not exists

    def test_root_delete(self, subdir_repo):
        """
        Check if deleting non-subdirectory page works.
        """

        title = u'ziew'
        filepath = os.path.join(subdir_repo.path, 'ziew')
        subdir_repo.save_text(title, self.text, self.author, self.comment,
                              parent=-1)
        exists = os.path.exists(filepath)
        assert exists
        subdir_repo.delete_page(title, self.author, self.comment)
        exists = os.path.exists(filepath)
        assert not exists

    def test_nonexistent_root_delete(self, subdir_repo):
        """
        Check if deleting non-existing non-subdirectory page works.
        """

        title = u'ziew2'
        filepath = os.path.join(subdir_repo.path, 'ziew2')
        exists = os.path.exists(filepath)
        assert not exists
        subdir_repo.delete_page(title, self.author, self.comment)
        exists = os.path.exists(filepath)
        assert not exists

    def test_create_parent(self, subdir_repo):
        """
        Make sure you can create a parent page of existing page.
        """

        subdir_repo.save_text(u'xxx/yyy', self.text, self.author, self.comment,
                              parent=-1)
        subdir_repo.save_text(u'xxx', self.text, self.author, self.comment,
                              parent=-1)
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx'))
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx/yyy'))
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx/Index'))

    def test_create_subpage(self, subdir_repo):
        """
        Make sure you can create a subpage of existing page.
        """

        subdir_repo.save_text(u'xxx', self.text, self.author, self.comment,
                              parent=-1)
        subdir_repo.save_text(u'xxx/yyy', self.text, self.author, self.comment,
                              parent=-1)
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx'))
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx/yyy'))
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx/Index'))
        tracked = subdir_repo._changectx()['xxx/Index']
        assert tracked

    def test_create_subsubpage(self, subdir_repo):
        """
        Make sure you can create a subpage of existing page.
        """

        subdir_repo.save_text(u'xxx', self.text, self.author, self.comment,
                              parent=-1)
        subdir_repo.save_text(u'xxx/yyy/zzz', self.text, self.author, self.comment,
                              parent=-1)
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx'))
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx/yyy'))
        assert not os.path.exists(os.path.join(subdir_repo.path, 'xxx/yyy/Index'))
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx/yyy/zzz'))
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx/Index'))

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

        files = {
            u'../some/+s page/ąęść?.txt':
                '_..%2Fsome%2F%2Bs%20page%2F%C4%85%C4%99%C5%9B%C4%87%3F.txt',
            u'simple': 'simple',
            u'COM1': '_COM1',
            u'_weird': '__weird',
            u'/absolute': '%2Fabsolute',
            u'slash/': 'slash%2F',
            u'%percent%': '%25percent%25',
        }
        for title, filename in files.iteritems():
            filepath = os.path.join(repo.path, filename)
            repo.save_text(title, self.text, self.author, self.comment,
                           parent=-1)
            exists = os.path.exists(filepath)
            print '%s -> %s' % (repr(title), filename)
            assert exists

    def test_check_path(self, repo):
        py.test.raises(hatta.error.ForbiddenErr, repo._check_path, "/")
        py.test.raises(hatta.error.ForbiddenErr, repo._check_path, "..")
        py.test.raises(hatta.error.ForbiddenErr, repo._check_path,
                       repo.path+"/..")
        path = os.path.join(repo.path, 'aaa')
        os.symlink('/', path)
        py.test.raises(hatta.error.ForbiddenErr, repo._check_path, path)
        path = os.path.join(repo.path, 'bbb')
        os.mkdir(path)
        py.test.raises(hatta.error.ForbiddenErr, repo._check_path, path)

    @py.test.mark.skipif("sys.platform == 'win32'")
    def test_symlinks(self, repo):
        """
        Make sure access to symlinks is blocked.
        """

        path = os.path.join(repo.path, self.filename)
        os.symlink('/', path)
        py.test.raises(hatta.error.ForbiddenErr, repo.save_text,
                       self.title, self.text, self.author, self.comment,
                       parent=-1)
        py.test.raises(hatta.error.ForbiddenErr, repo.open_page,
                       self.title)

    @py.test.mark.skipif("sys.platform == 'win32'")
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

    def test_directory_read(self, repo):
        """
        What happens when you try to read a directory as page.
        """

        path = os.path.join(repo.path, self.filename)
        os.mkdir(path)
        py.test.raises(hatta.error.ForbiddenErr, repo.open_page,
                       self.title)

    def test_directory_write(self, repo):
        """
        What happens when you try to write a directory as page.
        """

        path = os.path.join(repo.path, self.filename)
        os.mkdir(path)
        py.test.raises(hatta.error.ForbiddenErr, repo.save_text,
                       self.title, self.text, self.author, self.comment,
                       parent=-1)

    def test_directory_delete(self, repo):
        """
        What happens when you try to delete a directory as page.
        """

        path = os.path.join(repo.path, self.filename)
        os.mkdir(path)
        py.test.raises(hatta.error.ForbiddenErr, repo.delete_page,
                       self.title, self.author, self.comment)

    @py.test.mark.skipif("sys.platform == 'win32'")
    def test_symlink_delete(self, repo):
        """
        What happens when you try to delete a symlink as page.
        """

        path = os.path.join(repo.path, self.filename)
        os.symlink('/', path)
        py.test.raises(hatta.error.ForbiddenErr, repo.delete_page,
                       self.title, self.author, self.comment)


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

