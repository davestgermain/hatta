#!/usr/bin/python
# -*- coding: utf-8 -*-

import hatta

class TestParser(object):
    def test_extract_links(self):
        text = """[[one link]] some
text [[another|link]] more
text [[link]]"""
        links = list(hatta.WikiParser.extract_links(text))
        assert links == [
            ('one link', 'one link'),
            ('another', 'link'),
            ('link', 'link'),
        ]
