# -*- coding: utf-8 -*-

import werkzeug


def response(request, title, content, etag='', mime='text/html',
             rev=None, size=None):
    """Create a hatta.request.WikiResponse for a page."""

    response = WikiResponse(content, mimetype=mime)
    if rev is None:
        rev, date, author, comment = request.wiki.storage.page_meta(title)
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


class WikiResponse(werkzeug.BaseResponse, werkzeug.ETagResponseMixin,
                   werkzeug.CommonResponseDescriptorsMixin):
    """A typical HTTP response class made out of Werkzeug's mixins."""

    def make_conditional(self, request):
        ret = super(WikiResponse, self).make_conditional(request)
        # Remove all headers if it's 304, according to
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.3.5
        if self.status.startswith('304'):
            self.response = []
            try:
                del self.content_type
            except (AttributeError, KeyError, IndexError):
                pass
            try:
                del self.content_length
            except (AttributeError, KeyError, IndexError):
                pass
            try:
                del self.headers['Content-length']
            except (AttributeError, KeyError, IndexError):
                pass
            try:
                del self.headers['Content-type']
            except (AttributeError, KeyError, IndexError):
                pass
        return ret

