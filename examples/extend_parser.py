#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
An example of how you can extend Hatta's parser without touching the
original code.
"""

import hatta

class MyWikiParser(hatta.WikiParser):
    """Alternative WikiParser that uses smilies with noses."""

    smilies = {
        r':-)': "smile.png",
        r':-(': "frown.png",
        r':-P': "tongue.png",
        r':-D': "grin.png",
        r';-)': "wink.png",
    }

class MyWikiPageWiki(hatta.WikiPageWiki):
    parser = MyWikiParser

if __name__=='__main__':
    config = hatta.read_config()
    wiki = hatta.Wiki(config)
    wiki.mime_map['text/x-wiki'] = MyWikiPageWiki
    hatta.main(wiki=wiki)
