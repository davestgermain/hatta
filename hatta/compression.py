import gzip

try:
    import brotli
except ImportError:
    brotli = None

try:
    import zstandard
except ImportError:
    zstandard = None


class CompressionMiddleware:
    compress_types = set(
        [
            "text/",
            "application/javascript",
            "application/x-javascript",
            "application/json",
            "application/xml,",
        ]
    )

    def __init__(self, app):
        self.app = app

    def _parse_accept_encoding(self, environ):
        # breakpoint()
        accept_encoding_header = environ.get("HTTP_ACCEPT_ENCODING", "")
        headers = [("Vary", "Accept-Encoding")]
        encodings = {"identity": 1.0}

        for encoding in accept_encoding_header.split(","):
            if ";" in encoding:
                encoding, qvalue = encoding.split(";")
                encoding = encoding.strip()
                qvalue = qvalue.split("=", 1)[1]
                if qvalue != "":
                    encodings[encoding] = float(qvalue)
                else:
                    encodings[encoding] = 1.0
            else:
                encodings[encoding.strip()] = 1.0

        compression_method = None
        encoding = None

        if zstandard and encodings.get("zstd", 0) >= encodings["identity"]:
            encoding = "zstd"
            compression_method = self._compress_zstd
        elif brotli and encodings.get("br", 0) >= encodings["identity"]:
            encoding = "br"
            compression_method = self._compress_brotli
        elif encodings.get("gzip", 0) >= encodings["identity"]:
            encoding = "gzip"
            compression_method = self._compress_gzip

        elif encodings.get("*", 0) >= encodings["identity"]:
            if brotli is not None:
                encoding = "br"
                compression_method = self._compress_brotli
            else:
                encoding = "gzip"
                compression_method = self._compress_gzip

        if encoding:
            headers.append(("Content-Encoding", encoding))

        return compression_method, headers

    def _compress_zstd(self, result_iter, content_type):
        return [zstandard.compress(b"".join(result_iter), level=11)]

    def _compress_brotli(self, result_iter, content_type):
        if content_type.startswith("text/"):
            mode = brotli.MODE_TEXT
        else:
            mode = brotli.MODE_GENERIC
        return [brotli.compress(b"".join(result_iter), mode=mode)]

    def _compress_gzip(self, result_iter, content_type):
        return [gzip.compress(b"".join(result_iter))]

    def __call__(self, environ, start_response):
        compression_method, extra_headers = self._parse_accept_encoding(environ)
        if not compression_method:
            return self.app(environ, start_response)

        content_type = ""

        headers = []
        status = ""

        def _compress_response(wrapped_status, wrapped_headers):
            nonlocal content_type, status

            status = wrapped_status
            for name, value in wrapped_headers:
                if name == "Content-Type":
                    content_type = value
                headers.append((name, value))

        response = self.app(environ, _compress_response)
        for ctype in self.compress_types:
            if content_type.startswith(ctype):
                headers = [(k, v) for k, v in headers if k != "Content-Length"]
                response = compression_method(response, content_type)
                headers.extend(extra_headers)
                headers.append(("Content-Length", str(len(response[0]))))
                break
        start_response(status, headers)
        return response
