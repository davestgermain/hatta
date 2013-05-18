# -*- coding: utf-8 -*-

import werkzeug


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

