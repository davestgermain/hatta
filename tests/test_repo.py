#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import hatta
import py

# Patch for no gettext
hatta._ = lambda x:x

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

def pytest_funcarg__repo(request):
    repo_path = str(request.config.ensuretemp('repo'))
    request.addfinalizer(lambda: clear_directory(repo_path))
    return hatta.WikiStorage(repo_path)

class TestMercurialStorage(object):
    def test_save_text(self, repo):
        text = u"test text"
        title = u"test title"
        author = u"test author"
        comment = u"test comment"
        repo.save_text(title, text, author, comment, parent=-1)
        saved = repo.open_page(title).read()
        assert saved == text

    @py.test.mark.xfail
    def test_save_text_noparent(self, repo):
        text = u"test text"
        title = u"test title"
        author = u"test author"
        comment = u"test comment"
        repo.save_text(title, text, author, comment, parent=None)
        saved = repo.open_page(title).read()
        assert saved == text

    def test_save_merge_no_conflict(self, repo):
        text = u"test\ntext"
        title = u"test title"
        author = u"test author"
        comment = u"test comment"
        repo.save_text(title, text, author, comment, parent=-1)
        repo.save_text(title, text, author, comment, parent=-1)
        saved = repo.open_page(title).read()
        assert saved == text

    @py.test.mark.xfail
    def test_save_merge_line_conflict(self, repo):
        text = u"test\ntest"
        text1 = u"test\ntext"
        text2 = u"text\ntest"
        title = u"test title"
        author = u"test author"
        comment = u"test comment"
        repo.save_text(title, text, author, comment, parent=-1)
        repo.save_text(title, text1, author, comment, parent=0)
        repo.save_text(title, text2, author, comment, parent=0)
        saved = repo.open_page(title).read()
        assert saved == u'text\ntext'

    def test_delete(self, repo):
        text = u"text test"
        title = u"test title"
        author = u"test author"
        comment = u"test comment"
        repo.save_text(title, text, author, comment, parent=-1)
        assert title in repo
        repo.delete_page(title, author, comment)
        assert title not in repo
