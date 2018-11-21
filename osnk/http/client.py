import asyncio
import re
import ssl
import urllib.parse
from .utils import Headers


class Response:
    def __init__(self, reader, writer, status, response_headers,
                 response_content, request_headers, content):
        self.reader = reader
        self.writer = writer
        self.status = status
        self.headers = response_headers
        self.content = response_content


class RequestContextManager:
    first_line = re.compile(r'([^ ]+) ([^ ]+)')

    def __init__(self, url, *, method='GET', headers=None, data=None,
                 json=None, newline=b'\r\n', charset='utf-8'):
        self.url = url
        self.method = method
        self.headers = headers
        self.data = data
        self.json = json
        self.newline = newline
        self.charset = charset

    async def __aenter__(self):
        parsed = urllib.parse.urlparse(self.url)
        if parsed.scheme not in ['http', 'https']:
            raise ValueError('Available protocols are only HTTP or HTTPS')
        elif parsed.scheme == 'https':
            port = parsed.port or 443
            sc = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            reader, self.writer = await asyncio.open_connection(
                parsed.hostname, port, ssl=sc)
        else:
            port = parsed.port or 80
            reader, self.writer = await asyncio.open_connection(
                parsed.hostname, port)
        path = parsed.path or '/'
        if self.data:
            if isinstance(self.data, (bytes, bytearray)):
                content_type = 'application/octet-stream'
                content = self.data
            else:
                content_type = 'application/x-www-form-urlencoded'
                content = urllib.parse.urlencode(self.data).encode(self.charset)
        else:
            content_type = None
            content = None
        request_headers = Headers({'User-Agent': 'Unknown'})
        if content_type:
            request_headers['Content-Type'] = content_type
        for k, v in Headers(self.headers):
            request_headers[k] = v
        request_headers['Host'] = parsed.hostname
        if content:
            request_headers['Content-Length'] = len(content)
        target = path + ('?' + parsed.query if parsed.query else '')
        first = '{} {} HTTP/1.1'.format(self.method, target)
        self.writer.write(first.encode(self.charset))
        self.writer.write(self.newline)
        for name, value in request_headers:
            self.writer.write(name.encode(self.charset))
            self.writer.write(': '.encode(self.charset))
            self.writer.write(str(value).encode(self.charset))
            self.writer.write(self.newline)
        self.writer.write(self.newline)
        if content:
            self.writer.write(content)
        await self.writer.drain()
        first = await reader.readline()
        m = self.first_line.search(first.decode())
        if m:
            version, status = m.groups()
            status = int(status)
            response_headers = {}
            async for line in reader:
                line = line.strip()
                if not line:
                    break
                header = line.decode().split(':')
                if len(header) == 2:
                    name, value = header
                    name = name.strip()
                    key = name.lower()
                    value = value.strip()
                    try:
                        value = int(value)
                    except ValueError:
                        try:
                            value = float(value)
                        except ValueError:
                            pass
                    if key in response_headers:
                        if isinstance(response_headers[key], list):
                            response_headers[key].append(value)
                        else:
                            response_headers[key] = [response_headers[key], value]
                    else:
                        response_headers[key] = value
            response_headers = Headers(response_headers)
            if 'Content-Length' in response_headers:
                if isinstance(response_headers['Content-Length'], tuple):
                    content_length = response_headers['Content-Length'][0]
                else:
                    content_length = response_headers['Content-Length']
            else:
                content_length = 0
            response_content = bytearray()
            if isinstance(content_length, int):
                chunk = 1024
                while len(response_content) < content_length:
                    response_content.extend(await reader.read(chunk))
            return Response(reader, self.writer, status, response_headers,
                            response_content, request_headers, content)

    async def __aexit__(self, exc_type, exc, tb):
        self.writer.close()


def request(*args, **kwargs):
    return RequestContextManager(*args, **kwargs)


def get(url):
    return request(url)


def post(url, *, headers=None, data=None):
    return request(url, method='POST', headers=headers, data=data)

def delete(url):
    return request(url, method='DELETE')
