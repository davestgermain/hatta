#!/usr/bin/python
# -*- coding: utf-8 -*-

import werkzeug.exceptions
import pprint


class WikiError(werkzeug.exceptions.HTTPException):
    """Base class for all error pages."""

    def __init__(self, description=None, wiki=None):
        super(WikiError, self).__init__(description)
        self.wiki = wiki

    def get_body(self, environ):
        if self.wiki is None:
            return super(WikiError, self).get_body(environ)
        template = self.wiki.template_env.get_template('error.html')
        request = environ.get('werkzeug.request')
        context = {
            'wiki': self.wiki,
            'code': self.code,
            'name': self.name,
            'description': self.get_description(environ),
            'title': self.name,
            'request': request,
            'url': request.get_url,
            'download_url': request.get_download_url,
            'config': self.wiki.config,
            'environ': pprint.pformat(environ),
        }
        return template.stream(**context)


class BadRequest(WikiError):
    code = 400


class ForbiddenErr(WikiError):
    code = 403


class NotFoundErr(WikiError):
    code = 404


class RequestEntityTooLarge(WikiError):
    code = 413


class RequestURITooLarge(WikiError):
    code = 414


class UnsupportedMediaTypeErr(WikiError):
    code = 415


class NotImplementedErr(WikiError):
    code = 501


class ServiceUnavailableErr(WikiError):
    code = 503
