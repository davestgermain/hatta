#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
This is a set of unit tests for testing the repository storage of Hatta wiki
engine. To run it, run py.test (at least version 1.0) from the main Hatta
directory.
"""

import os

import hatta.storage.hg
import pytest
import mercurial.commands

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

@pytest.fixture
def repo(request, tmp_path):
    """
    This function is executed whenever a test needs a "repo" parameter.
    It creates a new WikiStorage object with Hatta repository in a
    temporary directory.
    """

    request.addfinalizer(lambda: clear_directory(tmp_path))
    return hatta.storage.hg.WikiStorage(tmp_path)

@pytest.fixture
def subdir_repo(request, tmp_path):
    """
    This function is executed whenever a test needs a "subdir_repo" parameter.
    It creates a new WikiSubdirectoryStorage object with Hatta repository in a
    temporary directory.
    """

    request.addfinalizer(lambda: clear_directory(tmp_path))
    return hatta.storage.hg.WikiSubdirectoryStorage(tmp_path)


def update(storage):
    mercurial.commands.update(storage.repo.ui, storage.repo)


class TestSubdirectoryStorage(object):
    """
    Tests for the WikiSubdirectoryStorage.
    """

    # pytestmark = pytest.mark.skip

    author = 'test author'
    text = 'test text'
    comment = 'test comment'

    title_encodings = {
        'test title': 'test title',
        '.test title': '%2Etest title',
        '../test title': '%2E./test title',
        'test/./title': 'test/%2E/title',
        'test/../title': 'test/%2E./title',
        'test//title': 'test/%2Ftitle',
        '/test/title': '%2Ftest/title',
    }


    def test_title_to_file(self, subdir_repo):
        """
        Test the modified filename escpaing.
        """

        for title, filename in self.title_encodings.items():
            escaped = subdir_repo._title_to_file(title)
            assert escaped == filename

    def test_filename(self, subdir_repo):
        """
        Check if the page's file is named properly.
        """

        for title, filename in self.title_encodings.items():
            filepath = os.path.join(subdir_repo.path, filename)
            subdir_repo.save_text(title, self.text, self.author, self.comment,
                                  parent=-1)
            update(subdir_repo)
            exists = os.path.exists(filepath)
            assert exists

    def test_subdirectory_delete(self, subdir_repo):
        """
        Check if empty subdirectories are removed on page delete.
        """

        title = 'foo/bar'
        filepath = os.path.join(subdir_repo.path, 'foo/bar')
        dirpath = os.path.join(subdir_repo.path, 'foo')
        subdir_repo.save_text(title, self.text, self.author, self.comment,
                              parent=-1)
        subdir_repo.delete_page(title, self.author, self.comment)
        update(subdir_repo)
        exists = os.path.exists(filepath)
        assert not exists
        exists = os.path.exists(dirpath)
        assert not exists

    def test_root_delete(self, subdir_repo):
        """
        Check if deleting non-subdirectory page works.
        """

        title = 'ziew'
        filepath = os.path.join(subdir_repo.path, 'ziew')
        subdir_repo.save_text(title, self.text, self.author, self.comment,
                              parent=-1)
        update(subdir_repo)
        exists = os.path.exists(filepath)
        assert exists
        subdir_repo.delete_page(title, self.author, self.comment)
        update(subdir_repo)
        exists = os.path.exists(filepath)
        assert not exists

    def test_nonexistent_root_delete(self, subdir_repo):
        """
        Check if deleting non-existing non-subdirectory page works.
        """

        title = 'ziew2'
        filepath = os.path.join(subdir_repo.path, 'ziew2')
        assert not os.path.exists(filepath)
        with pytest.raises(hatta.error.NotFoundErr):
            subdir_repo.delete_page(title, self.author, self.comment)
        update(subdir_repo)
        assert not os.path.exists(filepath)

    def test_create_parent(self, subdir_repo):
        """
        Make sure you can create a parent page of existing page.
        """

        subdir_repo.save_text('xxx/yyy', self.text, self.author, self.comment,
                              parent=-1)
        subdir_repo.save_text('xxx', self.text, self.author, self.comment,
                              parent=-1)
        update(subdir_repo)
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx'))
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx/yyy'))
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx/Index'))

    def test_create_subpage(self, subdir_repo):
        """
        Make sure you can create a subpage of existing page.
        """

        subdir_repo.save_text('xxx', self.text, self.author, self.comment,
                              parent=-1)
        subdir_repo.save_text('xxx/yyy', self.text, self.author, self.comment,
                              parent=-1)
        update(subdir_repo)
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx'))
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx/yyy'))
        assert os.path.exists(os.path.join(subdir_repo.path, 'xxx/Index'))
        tracked = subdir_repo.tip[b'xxx/Index']
        assert tracked

    def test_create_subsubpage(self, subdir_repo):
        """
        Make sure you can create a subpage of existing page.
        """

        subdir_repo.save_text('xxx', self.text, self.author, self.comment,
                              parent=-1)
        subdir_repo.save_text('xxx/yyy/zzz', self.text, self.author, self.comment,
                              parent=-1)
        update(subdir_repo)
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
    author = 'test author'
    text = 'test text'
    comment = 'test comment'

    def test_filename(self, repo):
        """
        Check if the page's file is named properly.
        """

        files = {
            '../some/+s page/ąęść?.txt':
                '_..%2Fsome%2F%2Bs%20page%2F%C4%85%C4%99%C5%9B%C4%87%3F.txt',
            'simple': 'simple',
            'COM1': '_COM1',
            '_weird': '__weird',
            '/absolute': '%2Fabsolute',
            'slash/': 'slash%2F',
            '%percent%': '%25percent%25',
        }
        for title, filename in files.items():
            filepath = os.path.join(repo.path, filename)
            repo.save_text(title, self.text, self.author, self.comment,
                           parent=-1)
            update(repo)
            exists = os.path.exists(filepath)
            print('%s -> %s' % (repr(title), filename))
            assert exists


    def test_directories_not_exist(self, repo):
        """
        Make sure directories are not reported as existing pages.
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
        pytest.raises(hatta.error.NotFoundErr, repo.get_revision,
                       self.title)


class TestStorage(object):
    """
    This class groups the general tests for Hatta storage that should
    always pass, no matter what configuration is used.
    """

    text = "test text"
    title = "test title"
    author = "test author"
    comment = "test comment"

    def test_save_text(self, repo):
        """
        Create a page and read its contents, verify that it matches.
        """

        repo.save_text(self.title, self.text, self.author, self.comment,
                       parent=-1)
        saved = repo.get_revision(self.title).text
        assert saved == self.text

    def test_save_text_noparent(self, repo):
        """
        Save a page with parent set to None.
        """

        repo.save_text(self.title, self.text, self.author, self.comment,
                       parent=None)
        saved = repo.get_revision(self.title).text
        assert saved == self.text

    def test_save_merge_no_conflict(self, repo):
        """
        Create a page two times, with the same content. Verify that
        it is merged correctly.
        """

        text = "test\ntext"
        repo.save_text(self.title, text, self.author, self.comment, parent=-1)
        repo.save_text(self.title, text, self.author, self.comment, parent=-1)
        saved = repo.get_revision(self.title).text
        assert saved == text

    def test_save_merge_line_conflict(self, repo):
        """
        Modify a page twice, saving conflicting content. Verify that merge
        markers are inserted properly.
        """

        text = """\
123
456
789"""
        text1 = """\
123
000
789"""
        text2 = """\
123
111
789"""
        repo.save_text(self.title, text, self.author, self.comment, parent=-1)
        repo.save_text(self.title, text1, self.author, self.comment, parent=0)
        repo.save_text(self.title, text2, self.author, self.comment, parent=0)
        saved = repo.get_revision(self.title).text
        assert saved == """\
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

    def test_all_pages(self, repo):
        """
        Test for page listing both using repo prefix or not.
        """

        repo.save_text(self.title, self.text, self.author, self.comment,
                       parent=-1)
        assert self.title in repo.all_pages()

        repo.repo_prefix = "prefix"
        repo.save_text(self.title, self.text, self.author, self.comment,
                       parent=-1)
        assert self.title in repo.all_pages()
