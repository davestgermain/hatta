#!/usr/bin/python
# -*- coding: utf-8 -*-

import gettext
import importlib
import os
import sys

import werkzeug
import werkzeug.routing
from werkzeug.exceptions import HTTPException
import jinja2

import hatta.error
import hatta.page
import hatta.search
import hatta.storage
import hatta.views
import hatta.request
import hatta.response


class WikiTitleConverter(werkzeug.routing.PathConverter):
    """Behaves like the path converter, but doesn't match the "+ pages"."""

    def to_url(self, value):
        return werkzeug.urls.url_quote(value.strip(), self.map.charset, safe="/")

    # regex = '([^+%]|%[^2]|%2[^Bb]).*?'
    regex = "[^/|+].*?"


class WikiAllConverter(werkzeug.routing.BaseConverter):
    """Matches everything."""

    regex = '.*?'


def init_gettext(language):
    if language is not None:
        try:
            translation = gettext.translation(
                'hatta',
                'locale',
                languages=[language],
            )
        except IOError:
            translation = gettext.translation(
                'hatta',
                fallback=True,
                languages=[language],
            )
    else:
        translation = gettext.translation('hatta', fallback=True)
    return translation


def init_template(translation, template_path):
    loaders = [jinja2.PackageLoader('hatta', 'templates')]

    if template_path is not None:
        loaders.insert(0, jinja2.FileSystemLoader(os.path.abspath(template_path)))

    template_env = jinja2.Environment(
        extensions=['jinja2.ext.i18n'],
        loader=jinja2.ChoiceLoader(loaders),
    )
    template_env.autoescape = True
    template_env.install_gettext_translations(translation, True)
    return template_env


class Wiki:
    """
    The main class of the wiki, handling initialization of the whole
    application and most of the logic.
    """
    storage_class = None
    index_class = hatta.search.whoosh_search.WikiSearch
    filename_map = hatta.page.filename_map
    mime_map = hatta.page.mime_map

    def __init__(self, config, site_id=None):
        if config.get_bool('show_version', False):
            sys.stdout.write("Hatta %s\n" % hatta.__version__)
            sys.exit()
        self.config = config

        self.language = config.get('language')
        translation = init_gettext(self.language)
        self.gettext = translation.gettext
        self.template_path = config.get('template_path')
        self.template_env = init_template(translation, self.template_path)
        self.path = os.path.abspath(config.get('pages_path', 'docs'))
        self.repo_path = config.get('repo_path')
        self.page_charset = config.get('page_charset', 'utf-8')
        self.menu_page = self.config.get('menu_page', 'Menu')
        self.front_page = self.config.get('front_page', 'Home')
        self.logo_page = self.config.get('logo_page', 'logo.png')
        self.locked_page = self.config.get('locked_page', 'Locked')
        self.site_name = self.config.get('site_name', 'Hatta Wiki')
        self.site_id = site_id or config.get('site_name')
        self.read_only = self.config.get_bool('read_only', False)
        self.allow_bulk_uploads = self.config.get_bool('allow_bulk_uploads', False)
        self.fallback_url = self.config.get('fallback_url')
        self.icon_page = self.config.get('icon_page')
        self.alias_page = self.config.get('alias_page', 'Alias')
        self.help_page = self.config.get('help_page', 'Help')
        self.math_url = self.config.get(
            'math_url',
            'mathjax',
        )
        self.pygments_style = self.config.get('pygments_style', 'tango')
        self.extension = self.config.get('extension')
        self.unix_eol = self.config.get_bool('unix_eol', False)
        self.recaptcha_public_key = self.config.get('recaptcha_public_key')
        self.recaptcha_private_key = self.config.get('recaptcha_private_key')
        self.subdirectories = self.config.get_bool('subdirectories', False)
        if self.subdirectories:
            self.storage_class = importlib.import_module('hatta.storage.hg').WikiSubdirectoryStorage
        else:
            vcs = self.config.get('vcs', 'hg')
            module = importlib.import_module('hatta.storage.{}'.format(vcs))
            self.storage_class = getattr(module, 'WikiStorage')
        self.storage = self.storage_class(
            self.path,
            charset=self.page_charset,
            _=self.gettext,
            unix_eol=self.unix_eol,
            extension=self.extension,
            repo_path=self.repo_path,
        )
        self.repo_path = self.storage.repo_path
        self.cache = self.setup_cache()
        self.index = self.index_class(self.storage.get_index_path(), self.language, self.page_charset)
        self.index.update(self)
        self.url_rules = hatta.views.URL.get_rules()
        self.views = hatta.views.URL.get_views()
        self.url_converters = {
            'title': WikiTitleConverter,
            'all': WikiAllConverter,
        }
        self.url_map = werkzeug.routing.Map(
            self.url_rules,
            converters=self.url_converters,
        )

    def setup_cache(self):
        """
        Setup the cache from configuration.
        If cache_path is set in the config,
        it can be set to file:///some/cache/path
        or memcached://127.0.0.1:port for memcached

        Otherwise, try to use storage.get_cache_path()
        as a cache directory. If cachelib can't be imported,
        no cache will be available.
        """
        cache = None
        cache_url = self.config.get('cache_path')
        if cache_url:
            # cache_url could be memcached://127.0....
            # or file:///some/path or /some/path
            split_url = cache_url.split('://', 1)
            if len(split_url) == 1:
                split_url = ('file://', split_url)
            proto, path = split_url
            if proto == 'memcached':
                from cachelib import MemcachedCache
                from hashlib import sha1
                cache = MemcachedCache(
                    path.split(','),
                    key_prefix=sha1(self.site_id.encode('utf8')).hexdigest()[:8]
                )
            elif proto == 'file':
                from cachelib import FileSystemCache
                cache = FileSystemCache(os.path.abspath(path))
        else:
            try:
                from cachelib import FileSystemCache
            except ImportError:
                pass
            else:
                cache = FileSystemCache(os.path.abspath(self.storage.get_cache_path()))
        return cache

    def add_url_rule(self, rule, name, func):
        """Let plugins add additional url rules."""

        self.url_rules.append(rule)
        self.views[name] = func
        self.url_map = werkzeug.routing.Map(
            self.url_rules,
            converters=self.url_converters,
        )

    @werkzeug.wsgi.responder
    def application(self, environ, start):
        """The main application loop."""

        adapter = self.url_map.bind_to_environ(environ)
        request = hatta.request.WikiRequest(self, adapter, environ)
        try:
            endpoint, values = adapter.match()
            view = self.views[endpoint]
            self.refresh()
            return view(request, **values)
        except HTTPException as err:
            return err

    def refresh(self):
        """Make sure we have the latest revision of storage."""
        storage_rev = self.storage.repo_revision
        index_rev = self.index.get_last_revision()
        if storage_rev != index_rev:
            self.storage.reopen()
