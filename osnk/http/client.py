import asyncio
import re
import ssl
import urllib.parse
from .utils import Headers

newline = b'\r\n'
first_line = re.compile(r'([^ ]+) ([^ ]+) (.*)')

# async def client(loop):
#     sc = ssl.create_default_context(ssl.Purpose.SERVER_AUTH,
#         cafile='selfsigned.cert')
#     reader, writer = yield from asyncio.open_connection(
#         'localhost', port, ssl=sc, loop=loop)
#     writer.write(b'ping\n')
#     yield from writer.drain()
#     data = yield from reader.readline()
#     assert data == b'pong\n', repr(data)
#     print("Client received {!r} from server".format(data))
#     writer.close()
#     print('Client done')

async def request(url, *, method='GET', headers=None, data=None,
                  json=None, newline=b'\r\n', charset='utf-8'):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ['http', 'https']:
        raise ValueError('Available protocols are only HTTP or HTTPS')
    elif parsed.scheme == 'https':
        port = parsed.port or 443
        sc = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        reader, writer = await asyncio.open_connection(parsed.hostname, port,
                                                       ssl=sc)
    else:
        port = parsed.port or 80
        reader, writer = await asyncio.open_connection(parsed.hostname, port)
    path = parsed.path or '/'
    if data:
        content_type = 'application/x-www-form-urlencoded'
        content = urllib.parse.urlencode(data).encode(charset)
    else:
        content_type = None
        content = None
    request_headers = Headers({'User-Agent': 'Unknown'})
    if content_type:
        request_headers['Content-Type'] = content_type
    for k, v in Headers(headers):
        request_headers[k] = v
    request_headers['Host'] = parsed.hostname
    request_headers['Content-Length'] = len(content)
    writer.write('{} {} HTTP/1.1'.format(method, path).encode(charset))
    writer.write(newline)
    for name, value in request_headers:
        writer.write(name.encode(charset))
        writer.write(': '.encode(charset))
        writer.write(str(value).encode(charset))
        writer.write(newline)
    writer.write(newline)
    if content:
        writer.write(content)
    await writer.drain()
    first = await reader.readline()
    m = first_line.search(first.decode())
    if m:
        version, status, message = m.groups()
        status = int(status)
        response_headers = {}
        async for line in reader:
            line = line.strip()
            if not line:
                break
            print(line)
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
            total = 0
            while total < content_length:
                response_content.extend(await reader.read(chunk))
                total += chunk
        return status, response_headers, response_content, request_headers, content


async def get(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ['http', 'https']:
        raise ValueError('Available protocols are only HTTP or HTTPS')
    path = parsed.path or '/'
    port = parsed.port or 80
    reader, writer = await asyncio.open_connection(parsed.hostname, port)
    d = """GET {} HTTP/1.1
Host: {}
User-Agent: curl/7.54.0
Accept: */*

""".format(path, parsed.hostname)
    # print('>', d.replace('\n', '\n> ')[:-2])
    packet = d.encode(charset).replace(newline, b'\n').replace(b'\n', newline)
    writer.write(packet)
    await writer.drain()

    headers = {}
    async for line in reader:
        line = line.strip()
        if not line:
            break
        header = line.decode().split(':')
        if len(header) == 2:
            name, value = header
            name = name.lower().strip()
            value = value.strip()
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass
            if name != 'content-length' or isinstance(value, int):
                headers[name] = value
    if headers:
        payload = bytearray()
        if 'content-length' in headers:
            chunk = 1024
            total = 0
            while total < headers['content-length']:
                payload.extend(await reader.read(chunk))
                total += chunk
        # for k, v in headers.items():
        #     print('<', '{}: {}'.format(k, v))
        print(bytes(payload))
    writer.close()
    # print('Client done')


async def main():
    # await get('https://httpbin.org/ip')
    r = await request(
        # 'http://httpbin.org/ip',
        'https://discordapp.com/api/webhooks/478765241543426050/JTl3lksY3F3L6uLUW8quqr4h4O_G-3BxpdVLAmU8HYjoOkI7uN8cf0NwLBkTM2n2FYML',
        method='POST',
        data={'username': 'hClient', 'content': 'Hello!'},
        headers={'Content-Type': 'application/x-www-form-urlencoded'})
    print(r)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()
