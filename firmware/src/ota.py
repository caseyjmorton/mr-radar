import json
import os
import socket
import ssl
import hashlib
from version import __version__

_MANIFEST_URL = 'https://github.com/caseyjmorton/mr-radar/releases/latest/download/manifest.json'


def _http_get(url, max_redirects=4):
    for _ in range(max_redirects + 1):
        tls = url.startswith('https://')
        rest = url[8 if tls else 7:]
        netloc, _, path_rest = rest.partition('/')
        path = '/' + path_rest
        host, _, portstr = netloc.partition(':')
        port = int(portstr) if portstr else (443 if tls else 80)

        addr = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
        s = socket.socket()
        s.settimeout(20)
        try:
            s.connect(addr)
            if tls:
                s = ssl.wrap_socket(s, server_hostname=host)
            req = ('GET %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: mr-radar-fw/%s\r\n\r\n'
                   % (path, host, __version__))
            s.write(req.encode())
            data = b''
            while True:
                try:
                    chunk = s.recv(4096)
                except Exception:
                    break
                if not chunk:
                    break
                data += chunk
        finally:
            s.close()

        sep = data.find(b'\r\n\r\n')
        if sep < 0:
            raise OSError('no header separator')
        headers = data[:sep]
        body = data[sep + 4:]
        status = int(headers.split(b' ', 2)[1])

        if status in (301, 302, 303, 307, 308):
            location = None
            for line in headers.split(b'\r\n')[1:]:
                if line.lower().startswith(b'location:'):
                    location = line.split(b':', 1)[1].strip().decode()
                    break
            if not location:
                raise OSError('redirect with no Location header')
            url = location
            continue

        if status != 200:
            raise OSError('HTTP %d' % status)
        return body

    raise OSError('too many redirects')


def _ver_tuple(s):
    try:
        return tuple(int(x) for x in s.split('.'))
    except Exception:
        return (0,)


def check(manifest_url=None):
    """Fetch manifest and compare versions.

    Returns (new_version_str, files_list) if a newer version is available,
    or None if already up to date.
    """
    body = _http_get(manifest_url or _MANIFEST_URL)
    manifest = json.loads(body)
    new_ver = manifest.get('version', '')
    if not new_ver or _ver_tuple(new_ver) <= _ver_tuple(__version__):
        return None
    return (new_ver, manifest.get('files', []))


def apply(files):
    """Download files to /update/, verify SHA256, install to /, then reboot.

    Each entry in files must have: path, url, sha256.
    Raises on any error before installing — leaves /update/ intact for inspection.
    """
    import machine

    try:
        os.mkdir('/update')
    except OSError:
        pass

    for i, f in enumerate(files):
        fname = f['path']
        url = f['url']
        expected = f['sha256']
        print('ota: [%d/%d] downloading %s' % (i + 1, len(files), fname))
        data = _http_get(url)
        h = hashlib.sha256()
        h.update(data)
        actual = ''.join('%02x' % b for b in h.digest())
        if actual != expected:
            raise ValueError('sha256 mismatch %s: expected %s got %s' % (fname, expected, actual))
        with open('/update/' + fname, 'wb') as out:
            out.write(data)
        print('ota: verified %s (%d bytes)' % (fname, len(data)))

    # All files downloaded and verified — install
    for f in files:
        fname = f['path']
        os.rename('/update/' + fname, '/' + fname)
        print('ota: installed /' + fname)

    try:
        os.rmdir('/update')
    except Exception:
        pass

    print('ota: update complete, rebooting')
    machine.reset()
