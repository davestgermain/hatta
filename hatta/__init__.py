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

from hatta.wiki import Wiki, WikiResponse, WikiRequest
from hatta.config import WikiConfig, read_config
from hatta.__main__ import main, application
from hatta.parser import WikiParser, WikiWikiParser
from hatta.storage import WikiStorage, WikiSubdirectoryStorage
from hatta.page import WikiPage, WikiPageText, WikiPageWiki
from hatta.page import WikiPageColorText, WikiPageFile, WikiPageImage

__version__ = '1.4.0dev'
project_name = 'Hatta'
project_url = 'http://hatta-wiki.org/'
project_description = 'Wiki engine that lives in Mercurial repository.'

