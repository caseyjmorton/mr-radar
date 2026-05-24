# mr-radar animated client: background fetch thread + radial PPI sweep.
#
# Two threads with strict ownership:
#   - fetch thread: pulls /frame into a threadsafe buffer (RAM + lock only).
#   - main thread:  runs the sweep animation and owns the display exclusively.
#
# Run after copying gc9a01py.py, config.py, sweep.py, settings.py, and portal.py:
#     mpremote connect /dev/ttyACM0 run radar.py

import network
import socket
import ssl
import time
import _thread

import framebuf

import gc9a01py as gc
import config
import portal
import settings as secrets
import sweep

FRAME_BYTES = 240 * 240 * 2   # rgb565, exactly 115200 bytes
ROTATION_MS = 60000           # one 360-degree sweep per minute
TARGET_MS = 45                # min frame period (~22 fps cap); speed is clock-driven
STATUS_MS  = 20_000           # minimum time to show the connection status screen

_lock = _thread.allocate_lock()
_latest = None                # most recent good frame (bytearray), or None

# Framebuf stores RGB565 little-endian; GC9A01 wants big-endian. Pre-swap all colors.
_S_BG     = 0x0000   # black
_S_WHITE  = 0xFFFF   # white
_S_GREEN  = 0xE007   # bright green  (0x07E0 BE)
_S_CYAN   = 0xFF07   # cyan          (0x07FF BE)
_S_GRAY   = 0x1084   # mid-gray      (0x8410 BE)
_S_YELLOW = 0xE0FF   # yellow        (0xFFE0 BE)


def _draw_status(tft, ssid, renderer_url, status_text, status_color):
    W, H = 240, 240
    buf = bytearray(W * H * 2)
    fb = framebuf.FrameBuffer(buf, W, H, framebuf.RGB565)
    fb.fill(_S_BG)

    def ct(text, y, color):
        fb.text(text, (W - len(text) * 8) // 2, y, color)

    ct('mr-radar', 50, _S_GREEN)
    fb.hline(60, 68, 120, _S_GRAY)

    if renderer_url:
        # Connected: help user find the settings page
        ct('Settings URL:', 86, _S_GRAY)
        ct(renderer_url[:22], 100, _S_CYAN)
        fb.hline(60, 118, 120, _S_GRAY)
        ct('Connected to:', 132, _S_GRAY)
        ct(ssid[:22], 146, _S_WHITE)
    else:
        # Connecting: show progress
        ct('WiFi:', 86, _S_GRAY)
        ct(ssid[:22], 100, _S_WHITE)
        ct('Status:', 120, _S_GRAY)
        ct(status_text, 134, status_color)

    tft.blit_buffer(buf, 0, 0, W, H)


def connect_wifi(timeout=20):
    wlan = network.WLAN(network.STA_IF)
    # Reset the interface first: a prior run left active/associating makes the
    # next connect() raise "Wifi Internal State Error".
    wlan.active(False)
    time.sleep_ms(100)
    wlan.active(True)
    if not wlan.isconnected():
        print("wifi: connecting to", secrets.WIFI_SSID)
        wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
        deadline = time.ticks_add(time.ticks_ms(), timeout * 1000)
        while not wlan.isconnected():
            if time.ticks_diff(deadline, time.ticks_ms()) < 0:
                raise OSError("wifi timeout (status %d)" % wlan.status())
            time.sleep_ms(200)
    print("wifi: connected", wlan.ifconfig()[0])
    return wlan


def parse_url(url):
    if url.startswith("https://"):
        tls = True
        rest = url[len("https://"):]
        default_port = 443
    elif url.startswith("http://"):
        tls = False
        rest = url[len("http://"):]
        default_port = 80
    else:
        raise ValueError("url must be http:// or https://")
    netloc, _, path = rest.partition("/")
    host, _, port = netloc.partition(":")
    return host, int(port) if port else default_port, ("/" + path).rstrip("/"), tls


def fetch_frame(host, port, base, tls):
    theme = getattr(secrets, "THEME", "vintage")
    path = "{}/frame?station={}&fmt=rgb565&theme={}".format(
        base, secrets.STATION, theme)
    addr = socket.getaddrinfo(host, port)[0][-1]
    s = socket.socket()
    try:
        s.connect(addr)
        if tls:
            # fly.io shares IPs across apps, so SNI (server_hostname) is required.
            # Cert is unverified - fine for public radar imagery.
            s = ssl.wrap_socket(s, server_hostname=host)
        s.write("GET {} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\n\r\n"
                .format(path, host).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = s.read(256)
            if not chunk:
                raise OSError("closed before headers")
            head += chunk
        split = head.index(b"\r\n\r\n") + 4
        header, body = head[:split], head[split:]
        if int(header.split(b" ", 2)[1]) != 200:
            raise OSError("HTTP error")

        buf = bytearray(FRAME_BYTES)
        mv = memoryview(buf)
        n = len(body)
        mv[0:n] = body
        while n < FRAME_BYTES:
            chunk = s.read(1024)
            if not chunk:
                break
            c = len(chunk)
            if n + c > FRAME_BYTES:
                c = FRAME_BYTES - n
            mv[n:n + c] = chunk[:c]
            n += c
            time.sleep_ms(0)          # yield so the sweep keeps animating
        if n != FRAME_BYTES:
            raise OSError("short frame %d" % n)
        return buf
    finally:
        s.close()


def fetch_loop(host, port, base, tls):
    # Build each frame in a fresh buffer, then swap the shared reference under the
    # lock. The animation thread only ever reads a fully-built buffer, so there is
    # no tearing and the lock is held for just the pointer swap.
    global _latest
    while True:
        try:
            if not network.WLAN(network.STA_IF).isconnected():
                connect_wifi()
            buf = fetch_frame(host, port, base, tls)
            _lock.acquire()
            try:
                _latest = buf
            finally:
                _lock.release()
            print("fetch: new frame")
        except Exception as e:
            print("fetch error:", e)
        time.sleep(ROTATION_MS // 1000)


def _render(scope, tft, src, a0, a1):
    scope.restore_trail()
    scope.restore_line(src)              # undo the previous AA line exactly
    scope.paint_wedge(src, a0, a1)
    scope.paint_trail(a1)
    scope.sweep_line(a1)
    _, y0, _, y1 = scope.dirty_rect(a1 - sweep.TRAIL_DEG, a1)
    scope.blit_band(tft, y0, y1)


def main():
    tft = config.make_display()
    boot_ms = time.ticks_ms()

    _draw_status(tft, secrets.WIFI_SSID, None, 'Connecting...', _S_YELLOW)
    wlan = connect_wifi()
    device_ip = wlan.ifconfig()[0]
    _draw_status(tft, secrets.WIFI_SSID, 'http://' + device_ip, 'Connected!', _S_GREEN)

    host, port, base, tls = parse_url(secrets.RENDERER_URL)
    print("renderer:", host, port, base, "tls" if tls else "plain")

    _thread.stack_size(24 * 1024)
    _thread.start_new_thread(portal.serve, ())
    _thread.stack_size((32 if tls else 16) * 1024)
    _thread.start_new_thread(fetch_loop, (host, port, base, tls))

    scope = sweep.Sweep()

    # Hold the status screen until the first frame arrives AND STATUS_MS has elapsed,
    # whichever takes longer.
    src = None
    while True:
        _lock.acquire()
        try:
            latest = _latest
        finally:
            _lock.release()
        if latest is not None:
            src = latest
        if src is not None and time.ticks_diff(time.ticks_ms(), boot_ms) >= STATUS_MS:
            break
        time.sleep_ms(100)

    scope.show_frame(tft, src)
    print("status screen done; starting sweep")

    pending = None
    start = time.ticks_ms()
    prev = 0.0

    while True:
        t0 = time.ticks_ms()

        _lock.acquire()
        try:
            latest = _latest
        finally:
            _lock.release()
        if latest is not None and latest is not src:
            pending = latest             # swap in new frames at a rotation boundary

        # Azimuth is driven by the wall clock, so a rotation is always 60 s
        # regardless of render speed - slow frames just paint bigger wedges.
        cur = (time.ticks_diff(t0, start) % ROTATION_MS) * 360.0 / ROTATION_MS

        if cur < prev:                   # wrapped past 360 deg: finish + swap
            _render(scope, tft, src, prev, 360.0)
            prev = 0.0
            if pending is not None:
                src = pending
                pending = None
        if cur > prev:
            _render(scope, tft, src, prev, cur)
            prev = cur

        dt = time.ticks_diff(time.ticks_ms(), t0)
        if dt < TARGET_MS:
            time.sleep_ms(TARGET_MS - dt)


if __name__ == '__main__':
    main()
