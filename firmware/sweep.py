# Radial PPI sweep renderer for mr-radar.
#
# Renders into an in-RAM RGB565 framebuffer (big-endian, matching both the
# renderer's output and the GC9A01) and blits only the dirty rectangle around the
# current sweep. The hot per-pixel loops are @micropython.native with the blend
# inlined (no per-pixel method calls), and the dirty-rect gather copies through a
# memoryview (no per-row allocation) - both matter a lot on this MCU.
#
# The effect: a line sweeps from center to edge at the current azimuth, painting
# the radar echoes it passes (copied from the source frame) and leaving them in
# place (persistence). A bright, anti-aliased sweep line marks the live azimuth.
# The line is an overlay: every pixel it touches is recorded so restore_line()
# can put those exact pixels back from the source next frame.

import math
import micropython
from array import array

SWEEP_COLOR = 0x07E0     # bright green, classic PPI sweep line
SWEEP_HALFWIDTH = 1.2    # perpendicular half-width (px); larger = softer/thicker
_MAX_LINE_PX = 1600      # capacity of the recorded line-pixel buffer

TRAIL_DEG  = 20          # angular width of the PPI trail glow behind the sweep
TRAIL_STEP = 0.5         # degrees between trail radials; <=0.5 keeps gaps under 1px at rim
_MAX_TRAIL_PX = 5000     # 40 radials * 119 px (r=0 skipped), with margin

# Pre-extracted SWEEP_COLOR channels for viper (no module attr lookup in hot loop)
_TRAIL_CR = (SWEEP_COLOR >> 11) & 0x1F
_TRAIL_CG = (SWEEP_COLOR >>  5) & 0x3F
_TRAIL_CB =  SWEEP_COLOR        & 0x1F


class Sweep:
    def __init__(self, size=240):
        self.size = size
        self.cx = size // 2
        self.cy = size // 2
        self.R = size // 2 - 1            # keeps every plotted pixel in-bounds
        self.fb = bytearray(size * size * 2)
        self._fbmv = memoryview(self.fb)         # zero-copy source for band blit
        self._line_px = array('i', bytes(4 * _MAX_LINE_PX))
        self._line_n = 0                 # number of valid entries in _line_px
        # pixel offsets stored as half-values (o//2) in uint16 little-endian pairs;
        # o is always even and max o//2 = 57599 < 65536, so 2 bytes per entry suffice.
        self._trail_px    = bytearray(2 * _MAX_TRAIL_PX)
        self._trail_saved = bytearray(2 * _MAX_TRAIL_PX)  # pre-blend fb values
        self._trail_n = 0

    @micropython.native
    def _radial_src(self, deg, src):
        a = math.radians(deg)
        ca = math.cos(a)
        sa = math.sin(a)
        cx = self.cx
        cy = self.cy
        size = self.size
        fb = self.fb
        for r in range(self.R + 1):
            o = ((cy + int(r * sa)) * size + (cx + int(r * ca))) * 2
            fb[o] = src[o]
            fb[o + 1] = src[o + 1]

    @micropython.native
    def _aa_radial(self, deg, color):
        # Anti-aliased center->edge line: step the major axis and blend every
        # nearby minor-axis pixel by perpendicular distance (normalized by pscale
        # so width is uniform at all angles). Blend is inlined; touched offsets
        # are recorded for restore_line().
        a = math.radians(deg)
        ca = math.cos(a)
        sa = math.sin(a)
        cx = self.cx
        cy = self.cy
        size = self.size
        fb = self.fb
        px = self._line_px
        n = self._line_n
        cap = _MAX_LINE_PX
        hw = SWEEP_HALFWIDTH
        chi = color >> 8
        clo = color & 0xFF
        cr = (color >> 11) & 0x1F
        cg = (color >> 5) & 0x3F
        cb = color & 0x1F
        ex = cx + self.R * ca
        ey = cy + self.R * sa
        if abs(ca) >= abs(sa):                       # x-major
            steps = int(abs(ex - cx))
            if steps:
                sx = 1 if ex >= cx else -1
                slope = (ey - cy) / (ex - cx)
                pscale = 1.0 / math.sqrt(1.0 + slope * slope)
                reach = (hw + 0.5) / pscale + 1.0
                for i in range(steps + 1):
                    x = cx + sx * i
                    if 0 <= x < size:
                        m = cy + slope * (sx * i)
                        yy = int(m - reach)
                        yend = int(m + reach)
                        while yy <= yend:
                            if 0 <= yy < size:
                                cov = hw + 0.5 - abs(yy - m) * pscale
                                if cov > 0:
                                    o = (yy * size + x) * 2
                                    if cov >= 1.0:
                                        fb[o] = chi
                                        fb[o + 1] = clo
                                    else:
                                        av = int(cov * 256)
                                        ia = 256 - av
                                        bg = (fb[o] << 8) | fb[o + 1]
                                        r = (cr * av + ((bg >> 11) & 0x1F) * ia) >> 8
                                        g = (cg * av + ((bg >> 5) & 0x3F) * ia) >> 8
                                        b = (cb * av + (bg & 0x1F) * ia) >> 8
                                        v = (r << 11) | (g << 5) | b
                                        fb[o] = v >> 8
                                        fb[o + 1] = v & 0xFF
                                    if n < cap:
                                        px[n] = o
                                        n += 1
                            yy += 1
        else:                                        # y-major
            steps = int(abs(ey - cy))
            if steps:
                sy = 1 if ey >= cy else -1
                slope = (ex - cx) / (ey - cy)
                pscale = 1.0 / math.sqrt(1.0 + slope * slope)
                reach = (hw + 0.5) / pscale + 1.0
                for i in range(steps + 1):
                    y = cy + sy * i
                    if 0 <= y < size:
                        m = cx + slope * (sy * i)
                        xx = int(m - reach)
                        xend = int(m + reach)
                        while xx <= xend:
                            if 0 <= xx < size:
                                cov = hw + 0.5 - abs(xx - m) * pscale
                                if cov > 0:
                                    o = (y * size + xx) * 2
                                    if cov >= 1.0:
                                        fb[o] = chi
                                        fb[o + 1] = clo
                                    else:
                                        av = int(cov * 256)
                                        ia = 256 - av
                                        bg = (fb[o] << 8) | fb[o + 1]
                                        r = (cr * av + ((bg >> 11) & 0x1F) * ia) >> 8
                                        g = (cg * av + ((bg >> 5) & 0x3F) * ia) >> 8
                                        b = (cb * av + (bg & 0x1F) * ia) >> 8
                                        v = (r << 11) | (g << 5) | b
                                        fb[o] = v >> 8
                                        fb[o + 1] = v & 0xFF
                                    if n < cap:
                                        px[n] = o
                                        n += 1
                            xx += 1
        self._line_n = n

    @micropython.native
    def _blend_radial(self, deg, alpha256):
        # Compute trig once in native (float ok here), convert to 11-bit fixed-point,
        # then hand off to the viper inner loop which is pure integer math.
        a = math.radians(deg)
        self._blend_trail_viper(int(math.sin(a) * 2048), int(math.cos(a) * 2048), alpha256)

    @micropython.viper
    def _blend_trail_viper(self, sa_fp: int, ca_fp: int, alpha256: int):
        # Hot inner loop: SWEEP_COLOR * alpha + fb * (1-alpha), saving pre-blend
        # fb values so restore_trail() can undo exactly without consulting src.
        # r=0 (center pixel) skipped: all radials converge there and would double-save.
        # Offsets stored as o//2 in little-endian uint16 pairs (o is always even,
        # max o//2 = 57599 < 65536) so ptr8 suffices for _trail_px.
        fb  = ptr8(self.fb)
        sv  = ptr8(self._trail_saved)
        px  = ptr8(self._trail_px)
        n   = int(self._trail_n)
        cap = int(_MAX_TRAIL_PX)
        cx  = int(self.cx)
        cy  = int(self.cy)
        sz  = int(self.size)
        R   = int(self.R)
        ia  = 256 - alpha256
        cr  = int(_TRAIL_CR)
        cg  = int(_TRAIL_CG)
        cb  = int(_TRAIL_CB)
        for r in range(1, R + 1):
            x = cx + ((r * ca_fp) >> 11)
            y = cy + ((r * sa_fp) >> 11)
            o = (y * sz + x) * 2
            hi = fb[o]
            lo = fb[o + 1]
            bg = (hi << 8) | lo
            rr = (cr * alpha256 + ((bg >> 11) & 0x1F) * ia) >> 8
            gg = (cg * alpha256 + ((bg >>  5) & 0x3F) * ia) >> 8
            bb = (cb * alpha256 + ( bg        & 0x1F) * ia) >> 8
            v  = (rr << 11) | (gg << 5) | bb
            if n < cap:
                sv[n * 2]     = hi
                sv[n * 2 + 1] = lo
                half = o >> 1
                px[n * 2]     = half & 0xFF
                px[n * 2 + 1] = half >> 8
                n += 1
            fb[o]     = v >> 8
            fb[o + 1] = v & 0xFF
        self._trail_n = n

    @micropython.viper
    def restore_trail(self):
        fb = ptr8(self.fb)
        sv = ptr8(self._trail_saved)
        px = ptr8(self._trail_px)
        n  = int(self._trail_n)
        for i in range(n - 1, -1, -1):
            half     = px[i * 2] | (px[i * 2 + 1] << 8)
            o        = half << 1
            fb[o]    = sv[i * 2]
            fb[o + 1] = sv[i * 2 + 1]

    def paint_trail(self, az):
        # Paint the PPI glow: TRAIL_DEG of green behind az, brightest near az, fading back.
        self._trail_n = 0
        steps = int(TRAIL_DEG / TRAIL_STEP)
        for i in range(steps):
            alpha256 = int(((i + 1) / steps) ** 2 * 180)  # quadratic ramp, ~70% max
            deg = (az - TRAIL_DEG + i * TRAIL_STEP) % 360
            self._blend_radial(deg, alpha256)

    def paint_wedge(self, src, a0, a1, step=0.25):
        # Repaint source echoes across the wedge [a0, a1). The fine step keeps the
        # rim gap-free (0.25 deg ~ 0.5 px at r=119).
        d = a0
        while d < a1:
            self._radial_src(d, src)
            d += step

    @micropython.native
    def restore_line(self, src):
        # Undo the previous sweep line by restoring its exact pixels from src
        # (or black if there is no frame yet).
        fb = self.fb
        px = self._line_px
        n = self._line_n
        if src is None:
            for i in range(n):
                o = px[i]
                fb[o] = 0
                fb[o + 1] = 0
        else:
            for i in range(n):
                o = px[i]
                fb[o] = src[o]
                fb[o + 1] = src[o + 1]

    def sweep_line(self, deg):
        self._line_n = 0
        self._aa_radial(deg, SWEEP_COLOR)

    def dirty_rect(self, a0, a1, pad=5):
        # Bounding box (clamped) of everything that changes between azimuths a0
        # and a1: the wedge plus the old/new sweep line + AA spread.
        cx = self.cx
        cy = self.cy
        R = self.R
        xs = Xs = cx
        ys = Ys = cy
        for d in (a0, a1):
            a = math.radians(d)
            x = cx + R * math.cos(a)
            y = cy + R * math.sin(a)
            if x < xs:
                xs = x
            if x > Xs:
                Xs = x
            if y < ys:
                ys = y
            if y > Ys:
                Ys = y
        x0 = int(xs) - pad
        y0 = int(ys) - pad
        x1 = int(Xs) + pad
        y1 = int(Ys) + pad
        if x0 < 0:
            x0 = 0
        if y0 < 0:
            y0 = 0
        if x1 > self.size - 1:
            x1 = self.size - 1
        if y1 > self.size - 1:
            y1 = self.size - 1
        return x0, y0, x1, y1

    def blit_band(self, tft, y0, y1):
        # Blit full-width rows [y0, y1] straight from the framebuffer with no
        # gather and no allocation: rows are contiguous in fb, so a single
        # memoryview slice is exactly the windowed pixel stream the panel wants.
        size = self.size
        tft._set_window(0, y0, size - 1, y1)
        tft._write(None, self._fbmv[y0 * size * 2:(y1 + 1) * size * 2])

    def show_frame(self, tft, src):
        # Paint the entire source frame at once and push it. Used for the first
        # frame so the image appears immediately instead of being revealed over a
        # full 60 s sweep.
        self.fb[:] = src
        self.blit(tft)

    def blit(self, tft):
        tft._set_window(0, 0, self.size - 1, self.size - 1)
        tft._write(None, self.fb)
