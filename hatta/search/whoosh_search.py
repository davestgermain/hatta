#!/usr/bin/python
# -*- coding: utf-8 -*-

from collections import defaultdict
import re
import os.path, os
import time
from concurrent.futures.thread import ThreadPoolExecutor

from whoosh import index, fields, query
from whoosh.filedb.filestore import FileStorage

from .. import error, page

POOL = ThreadPoolExecutor(max_workers=1)


class IndexManager:
    def __init__(self, index_dir):
        self.istore = FileStorage(index_dir)
        self.istore.create()
        self.indexes = {}

    def get_index(self, name):
        if name not in self.indexes:
            self.indexes[name] = self.istore.open_index(name)
        return self.indexes[name].refresh()

    def index_searcher(self, index_name):
        return self.get_index(index_name).searcher()

    def index_writer(self, index_name):
        return self.get_index(index_name).writer()

    def index_exists(self, index_name):
        return self.istore.index_exists(index_name)

    def create_index(self, index_name, schema):
        """
        schema config looks like:
        {
            fieldname: {
                    type: KEYWORD
                    kwargs: {kwargs}
                }
        }
        """
        constructed = {}
        for field, config in schema.items():
            klass = getattr(fields, config['type'].upper())
            if 'kwargs' in config:
                klass = klass(**config['kwargs'])
            constructed[field] = klass
        schema = fields.Schema(**constructed)
        index = self.istore.create_index(schema, indexname=index_name)
        self.indexes[index_name] = index
        return index

    def simple_search(self, index_name, words, limit=1000, field='content'):
        if isinstance(words, str):
            words = words.split()
        sq = query.And([query.Term(field, w) for w in words])
        return self.run_query(index_name, sq, limit=limit)

    def run_query(self, index_name, query, limit=1000):
        with self.index_searcher(index_name) as searcher:
            results = searcher.search(query, limit=limit)
            for result in results:
                yield result

    def get_index_revision(self, index_name):
        """Retrieve the last indexed repository revision."""
        try:
            with self.istore.open_file(index_name + '-rev') as fp:
                rev = fp.read().decode('utf8')
        except:
            rev = -1
        return rev

    def set_index_revision(self, index_name, rev):
        """Store the last indexed repository revision."""
        with self.istore.create_file(index_name + '-rev') as fp:
            fp.write(str(rev).encode('utf8'))



class WikiSearch:
    """
    Responsible for indexing words and links, for fast searching and
    backlinks. Uses a cache directory to store the index files.
    """

    word_pattern = re.compile(r"""\w[-~&\w]+\w""", re.UNICODE)
    jword_pattern = re.compile(
r"""[ｦ-ﾟ]+|[ぁ-ん～ー]+|[ァ-ヶ～ー]+|[0-9A-Za-z]+|"""
r"""[０-９Ａ-Ｚａ-ｚΑ-Ωα-ωА-я]+|"""
r"""[^- !"#$%&'()*+,./:;<=>?@\[\\\]^_`{|}"""
r"""‾｡｢｣､･　、。，．・：；？！゛゜´｀¨"""
r"""＾￣＿／〜‖｜…‥‘’“”"""
r"""（）〔〕［］｛｝〈〉《》「」『』【】＋−±×÷"""
r"""＝≠＜＞≦≧∞∴♂♀°′″℃￥＄¢£"""
r"""％＃＆＊＠§☆★○●◎◇◆□■△▲▽▼※〒"""
r"""→←↑↓〓∈∋⊆⊇⊂⊃∪∩∧∨¬⇒⇔∠∃∠⊥"""
r"""⌒∂∇≡≒≪≫√∽∝∵∫∬Å‰♯♭♪†‡¶◾"""
r"""─│┌┐┘└├┬┤┴┼"""
r"""━┃┏┓┛┗┣┫┻╋"""
r"""┠┯┨┷┿┝┰┥┸╂"""
r"""ｦ-ﾟぁ-ん～ーァ-ヶ"""
r"""0-9A-Za-z０-９Ａ-Ｚａ-ｚΑ-Ωα-ωА-я]+""", re.UNICODE)

    def __init__(self, storage, lang):
        self.storage = storage
        self.lang = lang
        if lang == "ja":
            self.split_text = self.split_japanese_text
        self.index = IndexManager(storage.get_index_path())
        self.initialize_index()

    def initialize_index(self):
        if not self.index.index_exists(self.name):
            schema = {
                'links': {
                    'type': 'KEYWORD',
                    'kwargs': {'stored': True}
                },
                'title': {
                    'type': 'ID',
                    'kwargs': {'stored': True, 'unique': True}
                },
                'content': {
                    'type': 'TEXT',
                },
                'has_links': {
                    'type': 'BOOLEAN',
                },
                'wanted': {
                    'type': 'KEYWORD',
                    'kwargs': {'stored': True}
                },
            }
            self.index.create_index(self.name, schema)

    @property
    def name(self):
        return 'wiki'

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

    def reindex(self, wiki, pages):
        with self.index.index_writer(self.name) as writer:
            with self.index.index_searcher(self.name) as searcher:
                for title in pages:
                    writer.delete_by_term('title', title, searcher=searcher)
            for title in pages:
                p = page.get_page(None, title, wiki)
                self.reindex_page(p, title, writer)
        self.empty = False
        rev = self.storage.repo_revision()
        self.set_last_revision(rev)

    def reindex_page(self, page, title, writer, text=None):
        """Updates the content of the database, needs locks around."""

        if text is None:
            get_text = getattr(page, 'plain_text', lambda: u'')
            try:
                text = get_text()
            except error.NotFoundErr:
                text = None

        extract_links = getattr(page, 'extract_links', None)
        links = []
        wanted = []
        if extract_links and text:
            for link, label in extract_links(text):
                qlink = link.replace(u' ', u'%20')
                label = label.replace(u' ', u'%20')
                links.append('%s:%s' % (qlink, label))
                if link[0] != '+' and link not in wanted and link not in self.storage:
                    wanted.append(qlink)
        else:
            links = []
        doc = {'title': str(title)}
        if links:
            doc['links'] = ' '.join(links)
            doc['has_links'] = True
        if wanted:
            doc['wanted'] = ' '.join(wanted)
        if text:
            doc['content'] = text
            writer.add_document(**doc)
        else:
            writer.delete_by_term('title', title)

    # public interface
    def get_last_revision(self):
        """Retrieve the last indexed repository revision."""
        return self.index.get_index_revision(self.name)

    def set_last_revision(self, rev):
        """Store the last indexed repository revision."""
        return self.index.set_index_revision(self.name, rev)

    def find(self, words):
        """Iterator of all pages containing the words, and their scores."""
        for result in self.index.simple_search(self.name, words, field='content'):
            title = result['title']
            score = int(result.score)
            yield score, title

    def update(self, wiki):
        """Reindex al pages that changed since last indexing."""
        last_rev = self.get_last_revision()
        if last_rev == -1:
            changed = self.storage.all_pages()
        else:
            changed = self.storage.changed_since(last_rev)
        changed = list(changed)
        if changed:
            # self.reindex(wiki, changed)
            POOL.submit(self.reindex, wiki, changed)

    def update_page(self, page, title, data=None, text=None):
        """Updates the index with new page content, for a single page."""
        if text is None and data is not None:
            if not isinstance(data, str):
                text = str(data, self.storage.charset, 'replace')
            else:
                text = ''
        with self.index.index_writer(self.name) as writer:
            with self.index.index_searcher(self.name) as s:
                writer.delete_by_term('title', title, searcher=s)
            self.reindex_page(page, title, writer, text=text)
        self.set_last_revision(self.storage.repo_revision())

    def orphaned_pages(self):
        """Gives all pages with no links to them."""
        linked = set()
        total = {p for p in self.storage}
        for doc in self.index.run_query(self.name, query.Every('has_links'), limit=10000):
            for link in doc['links'].split():
                link = link.split(':', 1)[0]
                linked.add(link.replace('%20', ' '))
        return sorted(total - linked)

    def wanted_pages(self):
        """Gives all pages that are linked to, but don't exist, together with
        the number of links."""
        wanted = defaultdict(int)
        for doc in self.index.run_query(self.name, query.Every('wanted'), limit=8000):
            for link in doc['wanted'].split(' '):
                wanted[link.replace('%20', ' ')] += 1
        items = [(count, link) for link, count in wanted.items()]
        items.sort(reverse=True)
        return items

    def page_backlinks(self, title):
        """Gives a list of pages linking to specified page."""
        title = title.replace(' ', '%20')
        sq = query.Prefix("links", title + ':')
        results = set()
        for doc in self.index.run_query(self.name, sq, limit=8000):
            results.add(doc['title'])
        return results

    def page_links(self, title):
        """Gives a list of links on specified page."""
        return [l[0] for l in self.page_links_and_labels(title)]

    def page_links_and_labels(self, title):
        with self.index.index_searcher(self.name) as searcher:
            doc = searcher.document(title=title)
            if doc:
                links = doc.get('links', '')
                for l in links.split():
                    link, label = l.split(':', 1)
                    yield link.replace('%20', ' '), label.replace('%20', ' ')
