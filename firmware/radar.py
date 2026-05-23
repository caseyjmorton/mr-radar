# mr-radar client loop: WiFi -> GET /frame?fmt=rgb565 -> blit -> sleep.
# Step 3 of firmware bring-up. Robustness (last-good-frame, status dot,
# watchdog) is step 4 and lives elsewhere; this is the happy path with just
# enough error handling to keep looping.
#
# Run after copying gc9a01py.py, config.py, and your filled-in secrets.py:
#     mpremote connect /dev/ttyACM0 run radar.py

import network
import socket
import time

import gc9a01py
import config
import secrets

FRAME_BYTES = 240 * 240 * 2  # rgb565, exactly 115200 bytes


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
    if not url.startswith("http://"):
        raise ValueError("only http:// is supported in this step")
    rest = url[len("http://"):]
    netloc, _, path = rest.partition("/")
    host, _, port = netloc.partition(":")
    return host, int(port) if port else 80, ("/" + path).rstrip("/")


def fetch_and_blit(tft, host, port, base):
    path = "{}/frame?station={}&fmt=rgb565&theme={}".format(
        base, secrets.STATION, secrets.THEME)
    addr = socket.getaddrinfo(host, port)[0][-1]
    s = socket.socket()
    try:
        s.connect(addr)
        s.send("GET {} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\n\r\n"
               .format(path, host).encode())

        # Read headers up to the blank line; keep any body bytes that came with
        # the last header read.
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = s.recv(256)
            if not chunk:
                raise OSError("connection closed before headers")
            head += chunk
        split = head.index(b"\r\n\r\n") + 4
        header_text, body = head[:split], head[split:]

        status = int(header_text.split(b" ", 2)[1])
        if status != 200:
            raise OSError("HTTP {}".format(status))
        if b"X-Partial-Data: 1" in header_text:
            print("warning: partial upstream data (stale tiles)")
        ts = None
        for line in header_text.split(b"\r\n"):
            if line.lower().startswith(b"x-radar-timestamp:"):
                ts = line.split(b":", 1)[1].strip().decode()

        # Stream the body straight into GRAM: set the window once (it ends with
        # RAMWR), then push data chunks. CS toggling between chunks is fine - the
        # write pointer holds until a new command is sent.
        tft._set_window(0, 0, 239, 239)
        written = 0
        if body:
            tft._write(None, body)
            written += len(body)
        buf = bytearray(1024)
        mv = memoryview(buf)
        while written < FRAME_BYTES:
            n = s.readinto(buf)
            if not n:
                break
            if written + n > FRAME_BYTES:
                n = FRAME_BYTES - written
            tft._write(None, mv[:n])
            written += n
        if written != FRAME_BYTES:
            raise OSError("short frame: {} of {} bytes".format(written, FRAME_BYTES))
        return ts
    finally:
        s.close()


def main():
    tft = config.make_display()
    tft.fill(gc9a01py.BLACK)
    wlan = connect_wifi()
    host, port, base = parse_url(secrets.RENDERER_URL)
    print("renderer:", host, port, base)

    while True:
        try:
            if not wlan.isconnected():
                wlan = connect_wifi()
            ts = fetch_and_blit(tft, host, port, base)
            print("frame ok ts=", ts)
        except Exception as e:
            print("frame error:", e)
        time.sleep(secrets.POLL_SECONDS)


main()
