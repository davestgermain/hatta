#!/usr/bin/python
# -*- coding: utf-8 -*-

import werkzeug.exceptions


class WikiError(werkzeug.exceptions.HTTPException):
    """Base class for all error pages."""

    def get_body(self, environ):
        request = environ.get('werkzeug.request')
        wiki = request.wiki
        context = {
            'wiki': wiki,
            'code': self.code,
            'name': self.name,
            'description': self.get_description(environ),
            'title': self.name,
            'request': request,
            'url': request.get_url,
            'download_url': request.get_download_url,
            'config': wiki.config,
        }
        template = wiki.template_env.get_template('error.html')
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
