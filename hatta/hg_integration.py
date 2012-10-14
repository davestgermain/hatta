#!/usr/bin/python
# -*- coding: utf-8 -*-

import os

from hatta.config import WikiConfig
from __main__ import main


def run_wiki(ui, repo, directory=None, **opts):
    """Start serving Hatta in the provided repository."""

    config = WikiConfig()
    config.set('pages_path', directory or os.path.join(repo.root, 'docs'))
    ui.write('Starting wiki at http://127.0.0.1:8080\n')
    main(config=config)

cmdtable = {
    'wiki': (
        run_wiki, [
        ],
        "hg wiki [options] directory",
    ),
}
