# -*- coding: utf-8 -*-
import datetime

from urllib.parse import quote
from werkzeug.wrappers import (
    Response,
)  # , ETagResponseMixin, CommonResponseDescriptorsMixin

OLD_DATE = datetime.datetime(2018, 1, 1, 0, 0, 0)


def response(
    request, title, content, etag="", mime="text/html", rev=None, size=None, date=None
):
    """Create a hatta.request.WikiResponse for a page."""

    response = WikiResponse(content, mimetype=mime)
    etag = "%s/%s/" % (etag, quote(title))
    if rev:
        etag += "%s/" % rev
    if date:
        # add a modified date for better conditional requests
        etag += date.isoformat()
        response.last_modified = date
    response.set_etag(etag)
    if size:
        response.content_length = size
    response.make_conditional(request)
    return response


class WikiResponse(Response):
    """A typical HTTP response class made out of Werkzeug's mixins."""

    def make_conditional(self, request):
        # default pages have an etag that ends with -1
        # since these are static files, add an old modified date
        if not self.last_modified:
            if self.get_etag()[0].endswith("/-1"):
                self.last_modified = OLD_DATE
        return super(WikiResponse, self).make_conditional(request)
