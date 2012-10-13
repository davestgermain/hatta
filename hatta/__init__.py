#!/usr/bin/env python
# -*- coding: utf-8 -*-

# @copyright: 2008-2009 Radomir Dopieralski <hatta@sheep.art.pl>
# @license: GNU GPL, see COPYING for details.

"""
Hatta Wiki is a wiki engine designed to be used with Mercurial repositories.
It requires Mercurial and Werkzeug python modules.

Hatta's pages are just plain text files (and also images, binaries, etc.) in
some directory in your repository. For example, you can put it in your
project's "docs" directory to keep documentation. The files can be edited both
from the wiki or with a text editor -- in either case the changes committed to
the repository will appear in the recent changes and in page's history.

See hatta.py --help for usage.
"""

# Exposed API
from wiki import Wiki, WikiResponse, WikiRequest
from config import WikiConfig, read_config
from __main__ import main
from parser import WikiParser, WikiWikiParser
from storage import WikiStorage, WikiSubdirectoryStorage
from page import WikiPage, WikiPageText, WikiPageWiki
from page import WikiPageColorText, WikiPageFile, WikiPageImage

# Project's metainformation
__version__ = '1.5.0'
project_name = 'Hatta'
project_url = 'http://hatta-wiki.org/'
project_description = 'Wiki engine that lives in Mercurial repository.'

# Make it work as Mercurial extension
from hg_integration import cmdtable
