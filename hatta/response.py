# -*- coding: utf-8 -*-

from werkzeug.urls import url_quote
from werkzeug.wrappers import Response #, ETagResponseMixin, CommonResponseDescriptorsMixin


def response(request, title, content, etag='', mime='text/html',
             rev=None, size=None):
    """Create a hatta.request.WikiResponse for a page."""

    response = WikiResponse(content, mimetype=mime)
    if rev is None:
        rev, date, author, comment = request.wiki.storage.page_meta(title)
        response.set_etag('%s/%s/%d-%s' % (etag,
                                            url_quote(title),
                                            rev, date.isoformat()))
    else:
        response.set_etag('%s/%s/%s' % (etag, url_quote(title),
                                         rev))
    if size:
        response.content_length = size
    response.make_conditional(request)
    return response


class WikiResponse(Response):
    """A typical HTTP response class made out of Werkzeug's mixins."""
