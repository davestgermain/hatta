This is a fork of [Hatta Wiki](http://hatta-wiki.org), with these changes:
* Supports python 3 only and Mercurial version 5.4+
* Supports using git repositories
* Uses whoosh for the search index

To install:

`pip install git+https://github.com/davestgermain/hatta.git`

To run against a git repo instead of mercurial:

`python -m hatta -d /some/repo -v git`
