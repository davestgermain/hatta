#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import re
import sqlite3
import thread

import hatta.error
import hatta.page

class WikiSearch(object):
    """
    Responsible for indexing words and links, for fast searching and
    backlinks. Uses a cache directory to store the index files.
    """

    word_pattern = re.compile(ur"""\w[-~&\w]+\w""", re.UNICODE)
    jword_pattern = re.compile(
ur"""[ｦ-ﾟ]+|[ぁ-ん～ー]+|[ァ-ヶ～ー]+|[0-9A-Za-z]+|"""
ur"""[０-９Ａ-Ｚａ-ｚΑ-Ωα-ωА-я]+|"""
ur"""[^- !"#$%&'()*+,./:;<=>?@\[\\\]^_`{|}"""
ur"""‾｡｢｣､･　、。，．・：；？！゛゜´｀¨"""
ur"""＾￣＿／〜‖｜…‥‘’“”"""
ur"""（）〔〕［］｛｝〈〉《》「」『』【】＋−±×÷"""
ur"""＝≠＜＞≦≧∞∴♂♀°′″℃￥＄¢£"""
ur"""％＃＆＊＠§☆★○●◎◇◆□■△▲▽▼※〒"""
ur"""→←↑↓〓∈∋⊆⊇⊂⊃∪∩∧∨¬⇒⇔∠∃∠⊥"""
ur"""⌒∂∇≡≒≪≫√∽∝∵∫∬Å‰♯♭♪†‡¶◾"""
ur"""─│┌┐┘└├┬┤┴┼"""
ur"""━┃┏┓┛┗┣┫┻╋"""
ur"""┠┯┨┷┿┝┰┥┸╂"""
ur"""ｦ-ﾟぁ-ん～ーァ-ヶ"""
ur"""0-9A-Za-z０-９Ａ-Ｚａ-ｚΑ-Ωα-ωА-я]+""", re.UNICODE)

    def __init__(self, cache_path, lang, storage):
        self._con = {}
        self.path = cache_path
        self.storage = storage
        self.lang = lang
        if lang == "ja":
            self.split_text = self.split_japanese_text
        self.filename = os.path.join(cache_path, 'index.sqlite3')
        if not os.path.isdir(self.path):
            self.empty = True
            os.makedirs(self.path)
        elif not os.path.exists(self.filename):
            self.empty = True
        else:
            self.empty = False
        self.init_db(self.con)

    def init_db(self, con):
        con.execute('CREATE TABLE IF NOT EXISTS titles '
                '(id INTEGER PRIMARY KEY, title VARCHAR);')
        con.execute('CREATE TABLE IF NOT EXISTS words '
                '(word VARCHAR, page INTEGER, count INTEGER);')
        con.execute('CREATE INDEX IF NOT EXISTS index1 '
                         'ON words (page);')
        con.execute('CREATE INDEX IF NOT EXISTS index2 '
                         'ON words (word);')
        con.execute('CREATE TABLE IF NOT EXISTS links '
            '(src INTEGER, target INTEGER, label VARCHAR, number INTEGER);')
        con.commit()

    @property
    def con(self):
        """Keep one connection per thread."""

        thread_id = thread.get_ident()
        try:
            return self._con[thread_id]
        except KeyError:
            connection = sqlite3.connect(self.filename)
            self._con[thread_id] = connection
            return connection

    def split_text(self, text):
        """Splits text into words"""

        for match in self.word_pattern.finditer(text):
            word = match.group(0)
            yield word.lower()

    def split_japanese_text(self, text):
        """Splits text into words, including rules for Japanese"""

        for match in self.word_pattern.finditer(text):
            word = match.group(0)
            got_japanese = False
            for m in self.jword_pattern.finditer(word):
                w = m.group(0)
                got_japanese = True
                yield w.lower()
            if not got_japanese:
                yield word.lower()

    def count_words(self, words):
        count = {}
        for word in words:
            count[word] = count.get(word, 0) + 1
        return count

    def title_id(self, title, con):
        c = con.execute('SELECT id FROM titles WHERE title=?;', (title,))
        idents = c.fetchone()
        if idents is None:
            con.execute('INSERT INTO titles (title) VALUES (?);', (title,))
            c = con.execute('SELECT LAST_INSERT_ROWID();')
            idents = c.fetchone()
        return idents[0]

    def update_words(self, title, text, cursor):
        title_id = self.title_id(title, cursor)
        cursor.execute('DELETE FROM words WHERE page=?;', (title_id,))
        if not text:
            return
        words = self.count_words(self.split_text(text))
        title_words = self.count_words(self.split_text(title))
        for word, count in title_words.iteritems():
            words[word] = words.get(word, 0) + count
        for word, count in words.iteritems():
            cursor.execute('INSERT INTO words VALUES (?, ?, ?);',
                             (word, title_id, count))

    def update_links(self, title, links_and_labels, cursor):
        title_id = self.title_id(title, cursor)
        cursor.execute('DELETE FROM links WHERE src=?;', (title_id,))
        for number, (link, label) in enumerate(links_and_labels):
            cursor.execute('INSERT INTO links VALUES (?, ?, ?, ?);',
                             (title_id, link, label, number))

    def orphaned_pages(self):
        """Gives all pages with no links to them."""

        con = self.con
        try:
            sql = ('SELECT title FROM titles '
                   'WHERE NOT EXISTS '
                   '(SELECT * FROM links WHERE target=title) '
                   'ORDER BY title;')
            for (title,) in con.execute(sql):
                yield unicode(title)
        finally:
            con.commit()

    def wanted_pages(self):
        """Gives all pages that are linked to, but don't exist, together with
        the number of links."""

        con = self.con
        try:
            sql = ('SELECT COUNT(*), target FROM links '
                   'WHERE NOT EXISTS '
                   '(SELECT * FROM titles WHERE target=title) '
                   'GROUP BY target ORDER BY -COUNT(*);')
            for (refs, db_title,) in con.execute(sql):
                title = unicode(db_title)
                yield refs, title
        finally:
            con.commit()

    def page_backlinks(self, title):
        """Gives a list of pages linking to specified page."""

        con = self.con  # sqlite3.connect(self.filename)
        try:
            sql = ('SELECT DISTINCT(titles.title) '
                   'FROM links, titles '
                   'WHERE links.target=? AND titles.id=links.src '
                   'ORDER BY titles.title;')
            for (backlink,) in con.execute(sql, (title,)):
                yield unicode(backlink)
        finally:
            con.commit()

    def page_links(self, title):
        """Gives a list of links on specified page."""

        con = self.con  # sqlite3.connect(self.filename)
        try:
            title_id = self.title_id(title, con)
            sql = 'SELECT target FROM links WHERE src=? ORDER BY number;'
            for (link,) in con.execute(sql, (title_id,)):
                yield unicode(link)
        finally:
            con.commit()

    def page_links_and_labels(self, title):
        con = self.con  # sqlite3.connect(self.filename)
        try:
            title_id = self.title_id(title, con)
            sql = ('SELECT target, label FROM links '
                   'WHERE src=? ORDER BY number;')
            for link, label in con.execute(sql, (title_id,)):
                yield unicode(link), unicode(label)
        finally:
            con.commit()

    def find(self, words):
        """Iterator of all pages containing the words, and their scores."""

        con = self.con
        try:
            ranks = []
            for word in words:
                # Calculate popularity of each word.
                sql = 'SELECT SUM(words.count) FROM words WHERE word LIKE ?;'
                rank = con.execute(sql, ('%%%s%%' % word,)).fetchone()[0]
                # If any rank is 0, there will be no results anyways
                if not rank:
                    return
                ranks.append((rank, word))
            ranks.sort()
            # Start with the least popular word. Get all pages that contain it.
            first_rank, first = ranks[0]
            rest = ranks[1:]
            sql = ('SELECT words.page, titles.title, SUM(words.count) '
                   'FROM words, titles '
                   'WHERE word LIKE ? AND titles.id=words.page '
                   'GROUP BY words.page;')
            first_counts = con.execute(sql, ('%%%s%%' % first,))
            # Check for the rest of words
            for title_id, title, first_count in first_counts:
                # Score for the first word
                score = float(first_count) / first_rank
                for rank, word in rest:
                    sql = ('SELECT SUM(count) FROM words '
                           'WHERE page=? AND word LIKE ?;')
                    count = con.execute(sql,
                        (title_id, '%%%s%%' % word)).fetchone()[0]
                    if not count:
                        # If page misses any of the words, its score is 0
                        score = 0
                        break
                    score += float(count) / rank
                if score > 0:
                    yield int(100 * score), unicode(title)
        finally:
            con.commit()

    def reindex_page(self, page, title, cursor, text=None):
        """Updates the content of the database, needs locks around."""

        if text is None:
            get_text = getattr(page, 'plain_text', lambda: u'')
            try:
                text = get_text()
            except hatta.error.NotFoundErr:
                text = None
                title_id = self.title_id(title, cursor)
                cursor.execute("DELETE FROM titles WHERE id=?;", (title_id,))
        extract_links = getattr(page, 'extract_links', None)
        if extract_links and text:
            links = extract_links(text)
        else:
            links = []
        self.update_links(title, links, cursor=cursor)
        if text is not None:
            self.update_words(title, text, cursor=cursor)

    def update_page(self, page, title, data=None, text=None):
        """Updates the index with new page content, for a single page."""

        if text is None and data is not None:
            text = unicode(data, self.storage.charset, 'replace')
        cursor = self.con.cursor()
        try:
            self.set_last_revision(self.storage.repo_revision())
            self.reindex_page(page, title, cursor, text)
            self.con.commit()
        except:
            self.con.rollback()
            raise

    def reindex(self, wiki, pages):
        """Updates specified pages in bulk."""

        cursor = self.con.cursor()
        try:
            for title in pages:
                page = hatta.page.get_page(None, title, wiki)
                self.reindex_page(page, title, cursor)
            self.con.commit()
            self.empty = False
        except:
            self.con.rollback()
            raise

    def set_last_revision(self, rev):
        """Store the last indexed repository revision."""

        # We use % here because the sqlite3's substitiution doesn't work
        # We store revision 0 as 1, 1 as 2, etc. because 0 means "no revision"
        self.con.execute('PRAGMA USER_VERSION=%d;' % (int(rev + 1),))

    def get_last_revision(self):
        """Retrieve the last indexed repository revision."""

        con = self.con
        c = con.execute('PRAGMA USER_VERSION;')
        rev = c.fetchone()[0]
        # -1 means "no revision", 1 means revision 0, 2 means revision 1, etc.
        return rev - 1

    def update(self, wiki):
        """Reindex al pages that changed since last indexing."""

        last_rev = self.get_last_revision()
        if last_rev == -1:
            changed = self.storage.all_pages()
        else:
            changed = self.storage.changed_since(last_rev)
        self.reindex(wiki, changed)
        rev = self.storage.repo_revision()
        self.set_last_revision(rev)
