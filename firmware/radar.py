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
TARGET_MS = 40                # min frame period (~25 fps cap); speed is clock-driven
STATUS_MS  = 20_000           # minimum time to show the connection status screen
# Frame fetches are kicked off when the wall clock reaches this second-within-minute,
# which is the sweep at 9 o'clock (180 deg). That leaves ~30 s before the rotation-
# boundary swap at second 15, so the throttled download finishes with margin to spare.
FETCH_TRIGGER_SEC = 45
FETCH_CHUNK       = 1024      # bytes per socket read while downloading a frame
FETCH_THROTTLE_MS = 80        # sleep between read chunks so the download never starves
                              # the render thread (spreads ~115 KB across ~10 s)

_lock = _thread.allocate_lock()
_latest = None                # most recent good frame (bytearray), or None
_ntp_synced = False
_clock_logged = False         # print clock info once on first render

# Framebuf stores RGB565 little-endian; GC9A01 wants big-endian. Pre-swap all colors.
_S_BG     = 0x0000   # black
_S_WHITE  = 0xFFFF   # white
_S_GREEN  = 0xE007   # bright green  (0x07E0 BE)
_S_CYAN   = 0xFF07   # cyan          (0x07FF BE)
_S_GRAY   = 0x1084   # mid-gray      (0x8410 BE)
_S_YELLOW = 0xE0FF   # yellow        (0xFFE0 BE)

# Clock overlay — same color as the sweep bar, no background (radar shows through).
# _CLOCK_COLOR = 0xE007: framebuf (LE) stores [0x07, 0xE0] per pixel, which is
# the same byte layout as big-endian 0x07E0 (green) in scope.fb. The clock is
# painted into scope.fb and delivered via blit_band — no separate blit_buffer.
_CLOCK_COLOR   = _S_GREEN
_CLOCK_BG      = 0x0000   # black (byte-order-neutral)

# Render text at 8x8 font ("HH:MM" = 5 chars = 40×8 px), then 2x-scale to display.
_CLOCK_RND_W   = 40
_CLOCK_RND_H   = 8
_CLOCK_TEXT_W  = _CLOCK_RND_W * 2    # 80 px wide at 2x
_CLOCK_TEXT_H  = _CLOCK_RND_H * 2    # 16 px tall at 2x
_CLOCK_TEXT_X  = (240 - _CLOCK_TEXT_W) // 2   # 80 (centered)
_CLOCK_TEXT_Y  = 26    # keeps text at same visual position as before

# Small render buffer for framebuf text(); pixel cache stores only lit (green) pixels.
# Cache is rebuilt once per minute; _stamp_clock_pixels writes ~640 pixels per frame.
_CLOCK_RND     = bytearray(_CLOCK_RND_W * _CLOCK_RND_H * 2)
_CLOCK_TMP     = framebuf.FrameBuffer(_CLOCK_RND, _CLOCK_RND_W, _CLOCK_RND_H, framebuf.RGB565)
_CLOCK_PX_BUF   = bytearray(_CLOCK_TEXT_W * _CLOCK_TEXT_H * 4)  # (off_lo, off_hi, b0, b1)
_CLOCK_SAVE_BUF = bytearray(_CLOCK_TEXT_W * _CLOCK_TEXT_H * 4)  # saved src values at those offsets
_CLOCK_PX_N    = 0
_CLOCK_SAVE_N  = 0
_CLOCK_LAST_STR = None   # cached time string; rebuild pixel cache only when this changes


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


def _try_ntp():
    global _ntp_synced
    try:
        import ntptime
        ntptime.settime()
        _ntp_synced = True
        print("ntp: synced, utc:", time.localtime())
    except Exception as e:
        print("ntp: failed:", e)


@micropython.native
def _unstamp_clock_pixels(src):
    sv = _CLOCK_SAVE_BUF
    n = _CLOCK_SAVE_N
    for i in range(n):
        off = sv[i * 4] | (sv[i * 4 + 1] << 8)
        src[off]     = sv[i * 4 + 2]
        src[off + 1] = sv[i * 4 + 3]


@micropython.native
def _stamp_clock_pixels(src):
    global _CLOCK_SAVE_N
    px = _CLOCK_PX_BUF
    sv = _CLOCK_SAVE_BUF
    n = _CLOCK_PX_N
    for i in range(n):
        off = px[i * 4] | (px[i * 4 + 1] << 8)
        sv[i * 4]     = px[i * 4]
        sv[i * 4 + 1] = px[i * 4 + 1]
        sv[i * 4 + 2] = src[off]
        sv[i * 4 + 3] = src[off + 1]
        src[off]     = px[i * 4 + 2]
        src[off + 1] = px[i * 4 + 3]
    _CLOCK_SAVE_N = n


def _paint_clock(fb, time_str):
    # Rebuild pixel cache only when the time string changes (once per minute).
    # Each call stamps cached green pixels into scope.fb; radar shows through the gaps.
    global _clock_logged, _CLOCK_LAST_STR, _CLOCK_PX_N
    if not _clock_logged:
        print("clock: ntp=%s time=%r" % (_ntp_synced, time_str))
        _clock_logged = True
    try:
        if time_str != _CLOCK_LAST_STR:
            _unstamp_clock_pixels(fb)    # restore src pixels overwritten by old clock
            _CLOCK_TMP.fill(_CLOCK_BG)
            _CLOCK_TMP.text(time_str, 0, 0, _CLOCK_COLOR)
            n = 0
            for sr in range(_CLOCK_RND_H):
                for sc in range(_CLOCK_RND_W):
                    so = (sr * _CLOCK_RND_W + sc) * 2
                    b0 = _CLOCK_RND[so]
                    b1 = _CLOCK_RND[so + 1]
                    if b0 != 0 or b1 != 0:
                        for dr in range(2):
                            y = _CLOCK_TEXT_Y + sr * 2 + dr
                            x_base = _CLOCK_TEXT_X + sc * 2
                            for dc in range(2):
                                off = (y * 240 + x_base + dc) * 2
                                _CLOCK_PX_BUF[n * 4]     = off & 0xFF
                                _CLOCK_PX_BUF[n * 4 + 1] = (off >> 8) & 0xFF
                                _CLOCK_PX_BUF[n * 4 + 2] = b0
                                _CLOCK_PX_BUF[n * 4 + 3] = b1
                                n += 1
            _CLOCK_PX_N = n
            _CLOCK_LAST_STR = time_str
        _stamp_clock_pixels(fb)
    except Exception as e:
        print("clock paint:", e)


def _clock_str(tz_secs):
    if not _ntp_synced:
        return "--:--"
    # Add 15 s so the text updates at second 45 (270° = 12 o'clock), the exact moment
    # the sweep reveals the top of the display — 15 s before the rotation boundary.
    lt = time.localtime(time.time() + tz_secs + 15)
    return "%02d:%02d" % (lt[3], lt[4])


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


def open_conn(host, port, tls):
    # Establish a (TLS) connection. The TLS handshake is ~600-800 ms of GIL-held
    # crypto on this MCU, so this is the expensive step the sweep must never wait on:
    # it runs once at startup (before the sweep) and only again on reconnect.
    t = time.ticks_ms()
    addr = socket.getaddrinfo(host, port)[0][-1]
    s = socket.socket()
    try:
        s.connect(addr)
        if tls:
            # fly.io shares IPs across apps, so SNI (server_hostname) is required.
            # Cert is unverified - fine for public radar imagery.
            s = ssl.wrap_socket(s, server_hostname=host)
    except Exception:
        s.close()
        raise
    print("conn: opened in", time.ticks_diff(time.ticks_ms(), t), "ms")
    return s


def fetch_over(s, host, base, throttle_ms=0):
    # Send one keep-alive GET on an already-open socket and read exactly one frame.
    # No handshake here, so the steady-state per-minute fetch never freezes the sweep.
    # The body read is capped to the remaining frame bytes so it never consumes into
    # the next keep-alive response.
    theme = getattr(secrets, "THEME", "vintage")
    path = "{}/frame?station={}&fmt=rgb565&theme={}".format(
        base, secrets.STATION, theme)
    s.write("GET {} HTTP/1.1\r\nHost: {}\r\nConnection: keep-alive\r\n\r\n"
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
    if n > FRAME_BYTES:
        n = FRAME_BYTES
    mv[0:n] = body[:n]
    while n < FRAME_BYTES:
        chunk = s.read(min(FETCH_CHUNK, FRAME_BYTES - n))
        if not chunk:
            raise OSError("short frame %d" % n)
        c = len(chunk)
        mv[n:n + c] = chunk
        n += c
        time.sleep_ms(throttle_ms)  # spread I/O so the sweep keeps animating
    return buf


def fetch_loop(host, port, base, tls):
    # Build each frame in a fresh buffer, then swap the shared reference under the
    # lock. The animation thread only ever reads a fully-built buffer, so there is
    # no tearing and the lock is held for just the pointer swap.
    #
    # The TLS connection is kept open across fetches (HTTP keep-alive) so the costly
    # handshake happens once at startup, not on every poll. A stale keep-alive socket
    # (server closed it during the idle gap) is detected on use and reopened once.
    #
    # Timing: the first frame is fetched immediately (unthrottled) so the sweep can
    # start without a long blank. After that, each fetch is kicked off when the wall
    # clock hits FETCH_TRIGGER_SEC (the sweep at 9 o'clock / 180 deg) and throttled
    # across ~10 s, landing the new frame well before the rotation swap at second 15.
    global _latest
    s = None
    first = True
    fetched = False
    while True:
        try:
            sec = int(time.time()) % 60
            if first or (sec == FETCH_TRIGGER_SEC and not fetched):
                if not network.WLAN(network.STA_IF).isconnected():
                    connect_wifi()
                    if s is not None:
                        try: s.close()
                        except Exception: pass
                        s = None
                throttle = 0 if first else FETCH_THROTTLE_MS
                if s is None:
                    s = open_conn(host, port, tls)
                try:
                    buf = fetch_over(s, host, base, throttle)
                except Exception:
                    # Stale keep-alive socket: reopen once (one handshake) and retry.
                    try: s.close()
                    except Exception: pass
                    s = open_conn(host, port, tls)
                    buf = fetch_over(s, host, base, throttle)
                _lock.acquire()
                try:
                    _latest = buf
                finally:
                    _lock.release()
                fetched = True
                first = False
                print("fetch: new frame")
            elif sec != FETCH_TRIGGER_SEC:
                fetched = False     # rearm once the trigger second has passed
        except Exception as e:
            print("fetch error:", e)
            fetched = False
            if s is not None:
                try: s.close()
                except Exception: pass
                s = None
        time.sleep_ms(200)


def _render(scope, tft, src, a0, a1):
    scope.restore_trail()
    scope.restore_line(src)
    scope.paint_wedge(src, a0, a1)
    scope.paint_trail(a1)
    scope.sweep_line(a1)
    _, y0, _, y1 = scope.dirty_rect(a1 - sweep.TRAIL_DEG, a1)
    scope.blit_band(tft, y0, y1)


def main():
    tft = config.make_display()
    boot_ms = time.ticks_ms()

    tz_secs = int(getattr(secrets, 'TZ_OFFSET', 0) * 3600)

    _draw_status(tft, secrets.WIFI_SSID, None, 'Connecting...', _S_YELLOW)
    wlan = connect_wifi()
    _try_ntp()
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

    _paint_clock(src, _clock_str(tz_secs))   # bake clock into the source frame
    scope.show_frame(tft, src)
    print("status screen done; starting sweep")

    pending = None
    start = time.ticks_ms()
    last_time_str = _clock_str(tz_secs)
    if _ntp_synced:
        prev = (float((time.time() + tz_secs) % 60) * 6.0 + 270.0) % 360.0
        _ntp_wall_sec = time.time() + tz_secs   # wall second at last ticks capture
        _ntp_sec_ms   = time.ticks_ms()         # ticks_ms when that second began
    else:
        prev = 0.0
        _ntp_wall_sec = 0
        _ntp_sec_ms   = 0

    while True:
        t0 = time.ticks_ms()

        _lock.acquire()
        try:
            latest = _latest
        finally:
            _lock.release()
        if latest is not None and latest is not src:
            pending = latest             # swap in new frames at a rotation boundary

        # Azimuth = wall-clock seconds-within-minute, smoothly interpolated.
        # ticks_ms() % 1000 is uncorrelated with time.time() sub-second, so we
        # track the ticks value at each second boundary and interpolate from there.
        # This gives smooth motion with no backward jumps.
        if _ntp_synced:
            wall_t = time.time() + tz_secs
            if wall_t != _ntp_wall_sec:
                _ntp_wall_sec = wall_t
                _ntp_sec_ms   = time.ticks_ms()
            frac = min(time.ticks_diff(time.ticks_ms(), _ntp_sec_ms) / 1000.0, 0.999)
            cur = (float(wall_t % 60 + frac) * 6.0 + 270.0) % 360.0
        else:
            cur = (time.ticks_diff(t0, start) % ROTATION_MS) * 360.0 / ROTATION_MS

        time_str = _clock_str(tz_secs)
        if time_str != last_time_str:
            _paint_clock(src, time_str)   # bake new time into current source frame
            last_time_str = time_str

        if cur < prev:                   # wrapped past 360 deg: finish + swap
            _render(scope, tft, src, prev, 360.0)
            prev = 0.0
            if pending is not None:
                src = pending
                pending = None
                _stamp_clock_pixels(src)  # bake current clock into newly arrived frame
        if cur > prev:
            _render(scope, tft, src, prev, cur)
            prev = cur

        dt = time.ticks_diff(time.ticks_ms(), t0)
        if dt < TARGET_MS:
            time.sleep_ms(TARGET_MS - dt)


if __name__ == '__main__':
    main()
