#!/usr/bin/python
# -*- coding: utf-8 -*-

import gettext
import os
import sys

import werkzeug
import werkzeug.routing
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
        return werkzeug.url_quote(value.strip(), self.map.charset, safe="/")

    regex = '([^+%]|%[^2]|%2[^Bb]).*'


class WikiAllConverter(werkzeug.routing.BaseConverter):
    """Matches everything."""

    regex = '.*'


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


class Wiki(object):
    """
    The main class of the wiki, handling initialization of the whole
    application and most of the logic.
    """
    storage_class = hatta.storage.WikiStorage
    index_class = hatta.search.WikiSearch
    filename_map = hatta.page.filename_map
    mime_map = hatta.page.mime_map

    def __init__(self, config):
        if config.get_bool('show_version', False):
            sys.stdout.write("Hatta %s\n" % hatta.__version__)
            sys.exit()
        self.dead = False
        self.config = config

        self.language = config.get('language')
        translation = init_gettext(self.language)
        self.gettext = translation.ugettext
        self.template_path = config.get('template_path')
        self.template_env = init_template(translation, self.template_path)
        self.path = os.path.abspath(config.get('pages_path', 'docs'))
        self.repo_path = config.get('repo_path')
        self.page_charset = config.get('page_charset', 'utf-8')
        self.menu_page = self.config.get('menu_page', u'Menu')
        self.front_page = self.config.get('front_page', u'Home')
        self.logo_page = self.config.get('logo_page', u'logo.png')
        self.locked_page = self.config.get('locked_page', u'Locked')
        self.site_name = self.config.get('site_name', u'Hatta Wiki')
        self.read_only = self.config.get_bool('read_only', False)
        self.fallback_url = self.config.get('fallback_url')
        self.icon_page = self.config.get('icon_page')
        self.alias_page = self.config.get('alias_page', 'Alias')
        self.help_page = self.config.get('help_page', 'Help')
        self.math_url = self.config.get(
            'math_url',
            'http://www.mathtran.org/cgi-bin/mathtran?tex=',
        )
        self.pygments_style = self.config.get('pygments_style', 'tango')
        self.extension = self.config.get('extension')
        self.unix_eol = self.config.get_bool('unix_eol', False)
        self.recaptcha_public_key = self.config.get('recaptcha_public_key')
        self.recaptcha_private_key = self.config.get('recaptcha_private_key')
        self.subdirectories = self.config.get_bool('subdirectories', False)
        if self.subdirectories:
            self.storage_class = hatta.storage.WikiSubdirectoryStorage
        self.storage = self.storage_class(
            self.path,
            self.page_charset,
            self.gettext,
            self.unix_eol,
            self.extension,
            self.repo_path,
        )
        self.repo_path = self.storage.repo_path
        self.cache = os.path.abspath(
            config.get(
                'cache_path',
                os.path.join(self.repo_path, '.hg', 'hatta', 'cache'),
            )
        )
        self.index = self.index_class(self.cache, self.language, self.storage)
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

    def add_url_rule(self, rule, name, func):
        """Let plugins add additional url rules."""

        self.url_rules.append(rule)
        self.views[name] = func
        self.url_map = werkzeug.routing.Map(
            self.url_rules,
            converters=self.url_converters,
        )

    @werkzeug.responder
    def application(self, environ, start):
        """The main application loop."""

        adapter = self.url_map.bind_to_environ(environ)
        request = hatta.request.WikiRequest(self, adapter, environ)
        try:
            endpoint, values = adapter.match()
            view = self.views[endpoint]
            return view(request, **values)
        except werkzeug.exceptions.HTTPException as err:
            return err

    def refresh(self):
        """Make sure we have the latest revision of storage."""

        storage_rev = self.storage.repo_revision()
        index_rev = self.index.get_last_revision()
        if storage_rev < index_rev:
            self.storage.reopen()
