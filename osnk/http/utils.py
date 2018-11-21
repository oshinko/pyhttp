import json
import io
import pathlib
import urllib.request


class ContentStream:
    def __init__(self, content, charset='utf-8'):
        if isinstance(content, str):
            self.content_type = 'text/plain'
            self.content = content.encode(charset)
            self.content_length = len(self.content)
        elif isinstance(content, (dict, list)):
            self.content_type = 'application/json'
            self.content = json.dumps(content).encode(charset)
            self.content_length = len(self.content)
        elif isinstance(content, (bytearray, bytes)):
            self.content_type = 'application/octet-stream'
            self.content = content
            self.content_length = len(self.content)
        elif isinstance(content, pathlib.Path):
            self.content_type = 'application/octet-stream'
            self.content = content
            self.content_length = content.stat().st_size
        elif content is None:
            self.content_type = None
            self.content = None
            self.content_length = 0
        else:
            m = "invalid type '{}'"
            raise ValueError(m.format(type(content).__name__))

    async def __aenter__(self):
        if isinstance(self.content, (bytearray, bytes)) or \
                self.content is None:
            self.stream = io.BytesIO(self.content)
        elif isinstance(self.content, pathlib.Path):
            self.stream = self.content.open('rb')
        else:
            m = "invalid type '{}'"
            raise ValueError(m.format(type(self.content).__name__))
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.stream.close()

    def __aiter__(self):
        return self

    async def __anext__(self):
        r = self.stream.read(1024)
        if not r:
            raise StopAsyncIteration
        return r


class Headers:
    def __init__(self, keyvals=None):
        if keyvals:
            if isinstance(keyvals, (dict, list, set, tuple)):
                self._keyvals = {}
                if isinstance(keyvals, dict):
                    pairs = keyvals.items()
                else:
                    pairs = keyvals
                for k, v in pairs:
                    key = k.lower()
                    if isinstance(v, list):
                        vals = v
                    elif isinstance(v, (set, tuple)):
                        vals = list(v)
                    else:
                        vals = [v]
                    if key in self._keyvals:
                        currentkey, currentvals = self._keyvals[key]
                        currentvals.extend(vals)
                    else:
                        self._keyvals[key] = (k, vals)
            elif isinstance(keyvals, self.__class__):
                self._keyvals = dict(keyvals._keyvals)
            else:
                raise ValueError()
        else:
            self._keyvals = {}

    def __setitem__(self, key, value):
        if isinstance(value, (list, set, tuple)):
            self._keyvals[key.lower()] = (key, value)
        else:
            self._keyvals[key.lower()] = (key, (value,))

    def __getitem__(self, key):
        r = self._keyvals.get(key.lower())
        if r:
            key, vals = r
            c = len(vals)
            if c == 1:
                return vals[0]
            elif c > 1:
                return tuple(vals)
        return None

    def __contains__(self, item):
        return isinstance(item, str) and item.lower() in self._keyvals

    def __repr__(self):
        params = {}
        for key, (k, v) in self._keyvals.items():
            if len(v) == 1:
                params[k] = v[0]
            else:
                params[k] = v
        return '{}({})'.format(self.__class__.__name__, params)

    def _generator(self):
        for key, (k, v) in self._keyvals.items():
            for x in v:
                yield k, x

    def __iter__(self):
        return self._generator()


class Arguments:
    def __init__(self, keyvals=None):
        if keyvals:
            if isinstance(keyvals, (dict, list, set, tuple)):
                self._keyvals = {}
                if isinstance(keyvals, dict):
                    pairs = keyvals.items()
                else:
                    pairs = keyvals
                for key, v in pairs:
                    if isinstance(v, list):
                        vals = v
                    elif isinstance(v, (set, tuple)):
                        vals = list(v)
                    else:
                        vals = [v]
                    if key in self._keyvals:
                        self._keyvals[key].extend(vals)
                    else:
                        self._keyvals[key] = vals
            elif isinstance(keyvals, self.__class__):
                self._keyvals = dict(keyvals._keyvals)
            else:
                raise ValueError()
        else:
            self._keyvals = {}

    def __setitem__(self, key, value):
        self._keyvals[key] = value

    def __getitem__(self, key):
        vals = self._keyvals.get(key)
        if vals:
            c = len(vals)
            if c == 1:
                return vals[0]
            elif c > 1:
                return vals
        return None

    def __contains__(self, item):
        return isinstance(item, str) and item in self._keyvals

    def __repr__(self):
        params = {}
        for key, vals in self._keyvals.items():
            if len(vals) == 1:
                params[key] = vals[0]
            else:
                params[key] = vals
        return '{}({})'.format(self.__class__.__name__, params)

    def _generator(self):
        for key, vals in self._keyvals.items():
            for x in vals:
                yield key, x

    def __iter__(self):
        return self._generator()


class Request:
    def __init__(self, transport, method, url, headers, content):
        self.transport = transport
        self.method = method
        self.url = url
        if isinstance(url, (list, tuple)):
            length = len(url)
            maxlen = 5
            if length >= maxlen:
                self.url = url[:maxlen]
            else:
                self.url = url
                for _ in range(maxlen - length):
                    self.url += (None,)
        if isinstance(headers, Headers):
            self.headers = headers
        else:
            self.headers = Headers(headers)
        self.content = content

    @property
    def args(self):
        if not hasattr(self, '_args'):
            shceme, host, port, path, query = self.url
            self._args = Arguments(urllib.parse.parse_qs(query))
        return self._args

    @property
    def form(self):
        if not hasattr(self, '_form'):
            if isinstance(self.content, str):
                s = self.content
            elif isinstance(self.content, (bytearray, bytes)):
                try:
                    s = self.content.decode()
                except UnicodeDecodeError:
                    s = None
            else:
                raise ValueError()
            self._form = Arguments(urllib.parse.parse_qs(s))
        return self._form

    def __repr__(self):
        return "{}('{}', {}, {}, {})".format(self.__class__.__name__,
                                             self.method, self.url,
                                             self.headers, self.content)
