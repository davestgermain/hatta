#!/usr/bin/python
# -*- coding: utf-8 -*-

import gettext
import os
import pkgutil
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

        self.language = config.get('language', None)
        if self.language is not None:
            try:
                translation = gettext.translation('hatta', 'locale',
                                        languages=[self.language])

            except IOError:
                translation = gettext.translation('hatta', fallback=True,
                                        languages=[self.language])
        else:
            translation = gettext.translation('hatta', fallback=True)
        self.gettext = translation.ugettext
        self.template_env = jinja2.Environment(
                            extensions=['jinja2.ext.i18n'],
                            loader=jinja2.PackageLoader('hatta', 'templates'),
                            )
        self.template_env.autoescape = True
        self.template_env.install_gettext_translations(translation, True)
        self.path = os.path.abspath(config.get('pages_path', 'docs'))
        self.repo_path = config.get('repo_path', None)
        self.page_charset = config.get('page_charset', 'utf-8')
        self.menu_page = self.config.get('menu_page', u'Menu')
        self.front_page = self.config.get('front_page', u'Home')
        self.logo_page = self.config.get('logo_page', u'logo.png')
        self.locked_page = self.config.get('locked_page', u'Locked')
        self.site_name = self.config.get('site_name', u'Hatta Wiki')
        self.read_only = self.config.get_bool('read_only', False)
        self.icon_page = self.config.get('icon_page', None)
        self.alias_page = self.config.get('alias_page', 'Alias')
        self.help_page = self.config.get('help_page', 'Help')
        self.math_url = self.config.get('math_url',
            'http://www.mathtran.org/cgi-bin/mathtran?tex=')
        self.pygments_style = self.config.get('pygments_style', 'tango')
        self.subdirectories = self.config.get_bool('subdirectories', False)
        self.extension = self.config.get('extension', None)
        self.unix_eol = self.config.get_bool('unix_eol', False)
        self.recaptcha_public_key = self.config.get(
                'recaptcha_public_key', None)
        self.recaptcha_private_key = self.config.get(
                'recaptcha_private_key', None)
        if self.subdirectories:
            self.storage = hatta.storage.WikiSubdirectoryStorage(self.path,
                self.page_charset, self.gettext, self.unix_eol, self.extension,
                self.repo_path)
        else:
            self.storage = self.storage_class(self.path, self.page_charset,
                self.gettext, self.unix_eol, self.extension,
                self.repo_path)
        self.repo_path = self.storage.repo_path
        self.cache = os.path.abspath(config.get('cache_path',
                os.path.join(self.repo_path, '.hg', 'hatta', 'cache')))
        self.index = self.index_class(self.cache, self.language, self.storage)
        self.index.update(self)
        self.url_rules = hatta.views.URL.rules(self)
        self.url_map = werkzeug.routing.Map(self.url_rules, converters={
            'title': WikiTitleConverter,
            'all': WikiAllConverter,
        })

    def add_url_rule(self, rule):
        """Let plugins add additional url rules."""

        self.url_rules.append(rule)
        self.url_map = werkzeug.routing.Map(self.url_rules, converters={
            'title': WikiTitleConverter,
            'all': WikiAllConverter,
        })

    def get_page(self, request, title):
        """Creates a page object based on page's mime type"""

        if title:
            try:
                page_class, mime = self.filename_map[title]
            except KeyError:
                mime = hatta.page.page_mime(title)
                major, minor = mime.split('/', 1)
                try:
                    page_class = self.mime_map[mime]
                except KeyError:
                    try:
                        plus_pos = minor.find('+')
                        if plus_pos > 0:
                            minor_base = minor[plus_pos:]
                        else:
                            minor_base = ''
                        base_mime = '/'.join([major, minor_base])
                        page_class = self.mime_map[base_mime]
                    except KeyError:
                        try:
                            page_class = self.mime_map[major]
                        except KeyError:
                            page_class = self.mime_map['']
        else:
            page_class = hatta.page.WikiPageSpecial
            mime = ''
        return page_class(self, request, title, mime)

    def response(self, request, title, content, etag='', mime='text/html',
                 rev=None, size=None):
        """Create a hatta.request.WikiResponse for a page."""

        response = hatta.response.WikiResponse(content, mimetype=mime)
        if rev is None:
            rev, date, author, comment = self.storage.page_meta(title)
            response.set_etag(u'%s/%s/%d-%s' % (etag,
                                                werkzeug.url_quote(title),
                                                rev, date.isoformat()))
        else:
            response.set_etag(u'%s/%s/%s' % (etag, werkzeug.url_quote(title),
                                             rev))
        if size:
            response.content_length = size
        response.make_conditional(request)
        return response

    def _check_lock(self, title):
        _ = self.gettext
        restricted_pages = [
            'scripts.js',
            'robots.txt',
        ]
        if self.read_only:
            raise hatta.error.ForbiddenErr(_(u"This site is read-only."))
        if title in restricted_pages:
            raise hatta.error.ForbiddenErr(_(u"""Can't edit this page.
It can only be edited by the site admin directly on the disk."""))
        if title in self.index.page_links(self.locked_page):
            raise hatta.error.ForbiddenErr(_(u"This page is locked."))

    def _serve_default(self, request, title, content=None, mime=None):
        """Some pages have their default content."""

        if title in self.storage:
            return self.download(request, title)
        if content is None:
            content = pkgutil.get_data('hatta', os.path.join('static', title))
        mime = mime or 'application/octet-stream'
        response = hatta.response.WikiResponse(
            content,
            mimetype=mime,
        )
        response.set_etag('/%s/-1' % title)
        response.make_conditional(request)
        return response


    @werkzeug.responder
    def application(self, environ, start):
        """The main application loop."""

        adapter = self.url_map.bind_to_environ(environ)
        request = hatta.request.WikiRequest(self, adapter, environ)
        try:
            try:
                endpoint, values = adapter.match()
                return endpoint(request, **values)
            except werkzeug.exceptions.HTTPException as err:
                return err
        finally:
            request.cleanup()
            del request
            del adapter
