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
        encodings = {
            "identity": 1.0,
            "gzip": 0,
            "br": 0,
            "zstd": 0,
            "*": 0,
        }

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

        if brotli and encodings["br"] >= encodings["identity"]:
            encoding = "br"
            compression_method = self._compress_brotli
        elif zstandard and encodings["zstd"] >= encodings["identity"]:
            encoding = "zstd"
            compression_method = self._compress_zstd
        elif encodings["gzip"] >= encodings["identity"]:
            encoding = "gzip"
            compression_method = self._compress_gzip
        elif encodings["*"] >= encodings["identity"]:
            if brotli is not None:
                encoding = "br"
                compression_method = self._compress_brotli
            elif zstandard is not None:
                encoding = "zstd"
                compression_method = self._compress_zstd
            else:
                encoding = "gzip"
                compression_method = self._compress_gzip

        if encoding:
            headers.append(("Content-Encoding", encoding))

        return compression_method, headers

    def _compress_zstd(self, result_iter, content_type):
        return [zstandard.compress(b"".join(result_iter), level=15)]

    def _compress_brotli(self, result_iter, content_type):
        if content_type.startswith(("text/", "application/javascript")):
            mode = brotli.MODE_TEXT
        else:
            mode = brotli.MODE_GENERIC
        return [brotli.compress(b"".join(result_iter), mode=mode)]

    def _compress_gzip(self, result_iter, content_type):
        return [gzip.compress(b"".join(result_iter))]

    def __call__(self, environ, start_response):
        compress_response, extra_headers = self._parse_accept_encoding(environ)
        if not compress_response:
            return self.app(environ, start_response)

        content_type = ""

        headers = []
        status = ""
        content_length = None

        def _check_content_type(wrapped_status, wrapped_headers):
            nonlocal content_type, content_length, status

            status = wrapped_status
            for name, value in wrapped_headers:
                if name == "Content-Type":
                    content_type = value
                elif name == "Content-Length":
                    content_length = value
                    continue
                headers.append((name, value))

        response = self.app(environ, _check_content_type)
        for ctype in self.compress_types:
            if content_type.startswith(ctype):
                response = compress_response(response, content_type)

                headers.extend(extra_headers)
                content_length = str(len(response[0]))
                break
        if content_length:
            headers.append(("Content-Length", content_length))
        start_response(status, headers)
        return response
