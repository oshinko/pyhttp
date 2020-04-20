import asyncio
import datetime
import json
import pathlib
import re
import sys
import traceback
from .utils import ContentStream, Headers, Request

pyversion = '.'.join(str(x) for x in sys.version_info[:3])
default_name = 'Python/' + pyversion


class HTTPServer:
    first_line = re.compile(r'([^ ]+) ([^ ]+) [^ ]+')

    def __init__(self, *, name=default_name, host='0.0.0.0', port=80,
                 newline=b'\r\n', charset='utf-8', headers=None, debug=False):
        self.name = name
        self.host = host
        self.port = port
        self.newline = newline
        self.charset = charset
        self.headers = Headers({'Server': self.name})
        for k, v in Headers(headers):
            self.headers[k] = v
        self.handlers = []
        self.debug = debug

    async def _not_found(self):
        content = json.dumps('404 Not Found').encode(self.charset)
        return content, 404, {'Content-Type': 'application/json'}

    def not_found(self, fn):
        self._not_found = fn
        return fn

    async def _method_not_allowed(self):
        content = json.dumps('405 Method Not Allowed').encode(self.charset)
        return content, 405, {'Content-Type': 'application/json'}

    def method_not_allowed(self, fn):
        self._method_not_allowed = fn
        return fn

    async def _error(self):
        content = json.dumps('500 Internal Server Error').encode(self.charset)
        return content, 500, {'Content-Type': 'application/json'}

    def error(self, fn):
        self._error = fn
        return fn

    def route(self, regex, methods=['GET']):
        if not regex.startswith('^'):
            regex = '^' + regex
        if not regex.endswith('$'):
            regex += '$'
        pattern = re.compile(regex)

        def wrapper(fn):
            for method in methods:
                self.handlers.append((method.upper(), pattern, fn))

        return wrapper

    async def write_response(self, writer, method, path, query, resp):
        max_returns = 3
        min_returns = 1
        if not isinstance(resp, tuple):
            resp = resp,
        resp = resp[:max_returns]
        returns = len(resp)
        if returns < min_returns:
            m = 'not enough values to unpack (expected {}, got {})'
            raise ValueError(m.format(min_returns, returns))
        for _ in range(max_returns - returns):
            resp += None,
        content, status, headers = resp
        if not status:
            status = 200
        headers = Headers(headers)
        for k, v in self.headers:
            headers[k] = v
        if 'Date' not in headers:
            d = datetime.datetime.utcnow()
            headers['Date'] = d.strftime('%a, %d, %b %Y %H:%M:%S GMT')
        try:
            stream = ContentStream(content, self.charset)
            if 'Content-Type' not in headers and stream.content_type:
                headers['Content-Type'] = stream.content_type
            headers['Content-Length'] = stream.content_length
        except ValueError:
            if 'Content-Type' not in headers:
                try:
                    headers['Content-Type'] = content.content_type
                except AttributeError:
                    raise ValueError('content-type is required')
            stream = content
        if self.debug:
            print('[{}] "{} {}" {}'.format(
                datetime.datetime.now(), method,
                path + '?' + query if query else path, status))
        writer.write('HTTP/1.1 {}'.format(status).encode(self.charset))
        writer.write(self.newline)
        for name, value in headers:
            writer.write(name.encode(self.charset))
            writer.write(': '.encode(self.charset))
            writer.write(str(value).encode(self.charset))
            writer.write(self.newline)
        writer.write(self.newline)
        await writer.drain()
        async with stream as s:
            async for b in s:
                writer.write(b)
                await writer.drain()

    async def handle(self, reader, writer, method, path, query):
        handler = None
        raw_headers = []
        async for line in reader:
            line = line.strip()
            if not line:
                break
            header = line.decode().split(':', 1)
            if len(header) == 2:
                name, value = header
                name = name.strip()
                value = value.strip()
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
                raw_headers.append((name, value))
        headers = Headers(raw_headers)
        if 'Content-Length' in headers:
            if isinstance(headers['Content-Length'], tuple):
                content_length = headers['Content-Length'][0]
            else:
                content_length = headers['Content-Length']
        else:
            content_length = 0
        content = bytearray()
        if isinstance(content_length, int):
            chunk = 1024
            while len(content) < content_length:
                content.extend(await reader.read(chunk))
        if 'Host' in headers:
            if isinstance(headers['Host'], tuple):
                h = headers['Host'][0]
            else:
                h = headers['Host']
            if ':' in h:
                host = h.split(':')[0]
            else:
                host = h
        else:
            host = self.host
        url = 'http', host, self.port, path, query
        request = Request(writer.transport, method, url, headers, content)
        resources = []
        for x, y, z in self.handlers:
            m = y.match(path)
            if m:
                resources.append((x, y, z, m.groups()))
        for x, y, z, parts in resources:
            if x == method:
                handler = z(request, *parts)
                break
        if resources and not handler:
            handler = self._method_not_allowed()
        if handler:
            resp = await handler
            if resp is None:
                resp = await self._not_found()
        else:
            resp = await self._not_found()
        await self.write_response(writer, method, path, query, resp)

    async def callback(self, reader, writer):
        try:
            first = await reader.readline()
            m = self.first_line.search(first.decode())
            if m:
                method, uri = m.groups()
                method = method.upper()
                parts = uri.split('?', 1)
                if len(parts) == 1:
                    path, = parts
                    query = None
                else:
                    path, query = parts
                try:
                    await self.handle(reader, writer, method, path, query)
                except ConnectionError:
                    raise
                except Exception:
                    r = await self._error()
                    await self.write_response(writer, method, path, query, r)
                    raise
        except Exception:
            print(traceback.format_exc(), file=sys.stderr)
        finally:
            writer.close()

    def start(self, loop=None):
        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop
        return asyncio.start_server(self.callback, self.host, self.port,
                                    loop=self.loop)


if __name__ == '__main__':
    port = sys.argv[1] if len(sys.argv) > 1 else 8000
    token = sys.argv[2] if len(sys.argv) > 2 else None
    server = HTTPServer(port=port, debug=True,
                        headers={'Access-Control-Allow-Origin': '*'})

    import functools

    def requires(token):
        def decorator(fn):
            @functools.wraps(fn)
            async def wrapper(request, *args, **options):
                if not token:
                    return await fn(request, *args, **options)
                elif 'authorization' in request.headers:
                    scheme = 'Bearer'
                    auth = request.headers['authorization']
                    if not isinstance(auth, tuple):
                        auth = auth,
                    for a in auth:
                        a = a.strip()
                        try:
                            s = a.lower().index(scheme.lower()) + len(scheme)
                            _token = a[s:].strip()
                        except ValueError:
                            _token = a
                        if _token == token:
                            return await fn(request, *args, **options)
                return None, 401, {'WWW-Authenticate': 'Bearer'}
            return wrapper
        return decorator

    @server.route('/(.*)', methods=['GET'])
    @requires(token)
    async def get(request, path):
        p = pathlib.Path.cwd() / path.replace('..', '')
        if p.is_dir():
            r = []
            for x in p.iterdir():
                if x.is_dir():
                    size = sum(y.stat().st_size for y in x.glob('**/*')
                               if y.is_file())
                    r.append((x.name, size))
                else:
                    r.append((x.name, x.stat().st_size))
            return sorted(r)
        elif p.is_file():
            return p

    @server.route('/(.*)', methods=['POST'])
    @requires(token)
    async def post(request, path):
        p = pathlib.Path.cwd() / path.replace('..', '')
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('ab') as f:
            f.write(request.content)
        return None, 200

    @server.route('/(.*)', methods=['DELETE'])
    @requires(token)
    async def delete(request, path):
        p = pathlib.Path.cwd() / path.replace('..', '')
        if p.is_file():
            try:
                p.unlink()
                return None, 200
            except FileNotFoundError:
                pass
        elif p.is_dir():
            try:
                p.rmdir()
                return None, 200
            except OSError:
                return None, 403

    @server.route('/(.*)', methods=['OPTIONS'])
    async def options(request, path):
        return None, 200, {'Allow': 'GET, POST, DELETE, OPTIONS',
                           'Access-Control-Allow-Headers': 'Authorization'}

    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(server.start(loop))
    start = 'Serving HTTP on {host} port {port} (http://{host}:{port}) ...'
    print(start.format(host=server.host, port=server.port))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        results.close()
        loop.run_until_complete(results.wait_closed())
        loop.close()
