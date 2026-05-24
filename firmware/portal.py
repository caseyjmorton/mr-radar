import network
import socket
import json
import time
import machine
import framebuf
import config as _config

_AP_SSID = 'mr-radar-setup'
_AP_PASS = ''.join('%02x' % b for b in machine.unique_id())
_CONFIG  = '/config.json'
_DEFAULTS = {
    'wifi_ssid':    '',
    'wifi_password': '',
    'station':      'KILN',
    'renderer_url': 'https://mr-radar.fly.dev',
    'theme':        'vintage',
    'poll_seconds': 60,
}

# Markers like _SSID_ are replaced at render time to avoid format-string issues
# with the CSS braces in this template.
_FORM_HTML = """\
<!DOCTYPE html><html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>mr-radar setup</title>
<style>
*{box-sizing:border-box}
body{font-family:sans-serif;max-width:420px;margin:32px auto;padding:0 16px;color:#222}
h1{margin:0 0 4px}
.sub{color:#666;margin:0 0 20px;font-size:.9em}
label{display:block;margin-top:14px;font-size:.85em;font-weight:600;color:#555}
input[type=text],input[type=password],input[type=number],select{width:100%;padding:8px 10px;margin-top:4px;border:1px solid #ccc;border-radius:4px;font-size:1em;background:#fff}
.radios{display:flex;gap:20px;margin-top:6px}
.radios label{display:flex;align-items:center;gap:6px;font-weight:400;font-size:1em;color:#222;margin:0;cursor:pointer}
.radios input{width:auto;margin:0}
button{display:block;width:100%;margin-top:24px;padding:12px;background:#2a7;color:#fff;border:none;border-radius:4px;font-size:1em;cursor:pointer;font-weight:600}
</style>
</head>
<body>
<h1>mr-radar setup</h1>
<p class="sub">Connected to <strong>_AP_SSID_</strong>. Configure your device below.</p>
<form method="POST" action="/save">
<label>WiFi Network (SSID)</label>
<input name="ssid" type="text" required value="_SSID_">
<label>WiFi Password</label>
<input name="password" type="password" value="_PASSWORD_">
<label>NEXRAD Station</label>
_STATION_INPUT_
<label>Renderer URL</label>
<input name="renderer_url" type="text" required value="_RENDERER_URL_">
<label>Theme</label>
<div class="radios">
<label><input type="radio" name="theme" value="modern"_MOD_SEL_> modern</label>
<label><input type="radio" name="theme" value="vintage"_VIN_SEL_> vintage</label>
</div>
<label>Poll interval (seconds, 10&#8211;600)</label>
<input name="poll_seconds" type="number" min="10" max="600" value="_POLL_SECONDS_">
<button type="submit">Save &amp; Reboot</button>
</form></body></html>"""

_SAVED_HTML = """\
<!DOCTYPE html><html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Saved</title>
<style>body{font-family:sans-serif;text-align:center;margin-top:80px;color:#222}</style>
</head>
<body>
<h1>&#10003; Saved</h1>
<p>Device is rebooting&hellip;</p>
<p id="s">Waiting for device to come back online.</p>
<script>
setTimeout(function poll(){
  fetch('/').then(function(r){
    if(r.ok){location.href='/';}else{setTimeout(poll,1000);}
  }).catch(function(){setTimeout(poll,1000);});
},5000);
</script>
</body></html>"""


def _load_config():
    try:
        with open(_CONFIG) as f:
            d = json.load(f)
        cfg = dict(_DEFAULTS)
        cfg.update(d)
        return cfg
    except Exception:
        return dict(_DEFAULTS)


def _save_config(cfg):
    with open(_CONFIG, 'w') as f:
        json.dump(cfg, f)


_stations_cache = None


def _fetch_stations(renderer_url):
    global _stations_cache
    if _stations_cache is not None:
        return _stations_cache
    try:
        tls = renderer_url.startswith('https://')
        rest = renderer_url[8 if tls else 7:]
        netloc, _, _ = rest.partition('/')
        host, _, portstr = netloc.partition(':')
        port = int(portstr) if portstr else (443 if tls else 80)
        addr = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
        s = socket.socket()
        s.settimeout(5)
        try:
            s.connect(addr)
            if tls:
                import ssl
                s = ssl.wrap_socket(s, server_hostname=host)
            s.write(('GET /stations HTTP/1.0\r\nHost: %s\r\n\r\n' % host).encode())
            data = b''
            while True:
                try:
                    chunk = s.recv(1024)
                except Exception:
                    break
                if not chunk:
                    break
                data += chunk
        finally:
            s.close()
        sep = data.find(b'\r\n\r\n')
        if sep < 0:
            return None
        _stations_cache = json.loads(data[sep + 4:])
        return _stations_cache
    except Exception as e:
        print('portal: stations fetch error:', e)
        return None


def _url_decode(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == '%' and i + 2 < len(s):
            try:
                out.append(chr(int(s[i+1:i+3], 16)))
                i += 3
                continue
            except Exception:
                pass
        if c == '+':
            out.append(' ')
        else:
            out.append(c)
        i += 1
    return ''.join(out)


def _parse_form(body):
    out = {}
    for pair in body.split('&'):
        if '=' in pair:
            k, _, v = pair.partition('=')
            out[_url_decode(k)] = _url_decode(v)
    return out


def _render_form(cfg, stations=None):
    if stations:
        cur = cfg['station']
        opts = ['<option value="">Select station…</option>']
        for st in stations:
            sel = ' selected' if st['id'] == cur else ''
            opts.append('<option value="%s"%s>%s &ndash; %s, %s</option>' % (
                st['id'], sel, st['id'], st['name'], st['state']))
        station_input = '<select name="station" required>' + ''.join(opts) + '</select>'
    else:
        station_input = ('<input name="station" type="text" maxlength="4" required'
                         ' style="text-transform:uppercase" value="' + cfg['station'] + '" placeholder="KILN">')
    h = _FORM_HTML
    h = h.replace('_AP_SSID_', _AP_SSID)
    h = h.replace('_SSID_', cfg['wifi_ssid'])
    h = h.replace('_PASSWORD_', cfg['wifi_password'])
    h = h.replace('_STATION_INPUT_', station_input)
    h = h.replace('_RENDERER_URL_', cfg['renderer_url'])
    h = h.replace('_MOD_SEL_', ' checked' if cfg['theme'] == 'modern' else '')
    h = h.replace('_VIN_SEL_', ' checked' if cfg['theme'] == 'vintage' else '')
    h = h.replace('_POLL_SECONDS_', str(cfg['poll_seconds']))
    return h


def _respond(conn, status, body):
    b = body.encode() if isinstance(body, str) else body
    hdr = (
        'HTTP/1.1 ' + status + '\r\n'
        'Content-Type: text/html; charset=utf-8\r\n'
        'Content-Length: ' + str(len(b)) + '\r\n'
        'Connection: close\r\n'
        '\r\n'
    ).encode()
    conn.sendall(hdr + b)


def _handle(conn, cfg):
    saved_cfg = None
    try:
        raw = b''
        while b'\r\n\r\n' not in raw:
            chunk = conn.recv(512)
            if not chunk:
                return cfg
            raw += chunk

        sep = raw.index(b'\r\n\r\n')
        header_str = raw[:sep].decode('utf-8', 'ignore')
        body_partial = raw[sep + 4:]

        first_line = header_str.split('\r\n', 1)[0]
        parts = first_line.split(' ', 2)
        if len(parts) < 2:
            return cfg
        method, path = parts[0], parts[1]

        if method == 'GET':
            stations = _fetch_stations(cfg.get('renderer_url', ''))
            _respond(conn, '200 OK', _render_form(cfg, stations))

        elif method == 'POST' and path == '/save':
            cl = 0
            for line in header_str.split('\r\n')[1:]:
                if line.lower().startswith('content-length:'):
                    cl = int(line.split(':', 1)[1].strip())
            body = body_partial
            while len(body) < cl:
                chunk = conn.recv(512)
                if not chunk:
                    break
                body += chunk

            form = _parse_form(body.decode('utf-8', 'ignore'))
            saved_cfg = {
                'wifi_ssid':    form.get('ssid', ''),
                'wifi_password': form.get('password', ''),
                'station':      form.get('station', 'KILN').upper()[:4],
                'renderer_url': form.get('renderer_url', _DEFAULTS['renderer_url']).rstrip('/'),
                'theme':        form.get('theme', 'modern'),
                'poll_seconds': int(form.get('poll_seconds', 60)),
            }
            _save_config(saved_cfg)
            _respond(conn, '200 OK', _SAVED_HTML)

        else:
            _respond(conn, '404 Not Found', '<h1>Not found</h1>')

    except Exception as e:
        print('portal: handle error:', e)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if saved_cfg is not None:
        time.sleep(2)
        machine.reset()

    return cfg


def _sw(c):
    # Byte-swap a big-endian RGB565 color for framebuf (which stores little-endian).
    # framebuf stores [LSB, MSB]; GC9A01 wants [MSB, LSB], so we pre-swap.
    return ((c & 0xFF) << 8) | (c >> 8)

_BG    = 0x0000          # black
_WHITE = 0xFFFF          # white
_GREEN = _sw(0x07E0)     # bright green
_CYAN  = _sw(0x07FF)     # cyan
_GRAY  = _sw(0x8410)     # medium gray


def _draw_portal_screen():
    W, H = 240, 240
    buf = bytearray(W * H * 2)
    fb = framebuf.FrameBuffer(buf, W, H, framebuf.RGB565)
    fb.fill(_BG)

    def ct(text, y, color):
        fb.text(text, (W - len(text) * 8) // 2, y, color)

    ct('mr-radar', 55, _GREEN)
    fb.hline(60, 73, 120, _GRAY)
    ct('WiFi:', 85, _GRAY)
    ct(_AP_SSID, 99, _WHITE)
    ct('Password:', 117, _GRAY)
    ct(_AP_PASS, 131, _WHITE)
    ct('Then open:', 151, _GRAY)
    ct('192.168.4.1', 165, _CYAN)

    try:
        tft = _config.make_display()
        tft.blit_buffer(buf, 0, 0, W, H)
    except Exception as e:
        print('portal: display error:', e)


def run():
    print('portal: starting access point...')
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=_AP_SSID, authmode=3, password=_AP_PASS)  # WPA2

    deadline = time.ticks_add(time.ticks_ms(), 10_000)
    while not ap.active():
        if time.ticks_diff(deadline, time.ticks_ms()) < 0:
            print('portal: AP failed to start')
            return
        time.sleep_ms(100)

    print('portal: AP up —', _AP_SSID, 'pass:', _AP_PASS, '— open http://192.168.4.1')
    _draw_portal_screen()

    cfg = _load_config()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    srv.bind(('0.0.0.0', 80))
    srv.listen(2)

    while True:
        conn, addr = srv.accept()
        print('portal: connection from', addr)
        cfg = _handle(conn, cfg)


def serve():
    """Settings HTTP server for STA (radar) mode. Same form as the captive portal.
    Blocks forever; start in a background thread."""
    cfg = _load_config()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    srv.bind(('0.0.0.0', 80))
    srv.listen(2)
    print('settings: server listening on :80')
    while True:
        conn, addr = srv.accept()
        print('settings: connection from', addr)
        cfg = _handle(conn, cfg)
