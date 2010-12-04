#!/usr/bin/python
# -*- coding: utf-8 -*-

import werkzeug.exceptions


class WikiError(werkzeug.exceptions.HTTPException):
    """Base class for all error pages."""


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
