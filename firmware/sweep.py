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

SWEEP_COLOR = 0x07E0     # bright green, classic PPI sweep line
SWEEP_HALFWIDTH = 1.2    # perpendicular half-width (px); larger = softer/thicker
_MAX_LINE_PX = 1600      # capacity of the recorded line-pixel buffer
# Coverage constant for the AA line, prescaled to the 0..256 alpha range:
# av = _AA_C0 - perp_distance*256, where av>=256 is full color and av>0 is a blend.
_AA_C0 = int((SWEEP_HALFWIDTH + 0.5) * 256)

TRAIL_DEG  = 20          # angular width of the PPI trail glow behind the sweep
TRAIL_STEP = 0.5         # degrees between trail radials; <=0.5 keeps gaps under 1px at rim
_MAX_TRAIL_PX = 5000     # 40 radials * 119 px (r=0 skipped), with margin

# Pre-extracted SWEEP_COLOR channels for viper (no module attr lookup in hot loop)
_TRAIL_CR = (SWEEP_COLOR >> 11) & 0x1F
_TRAIL_CG = (SWEEP_COLOR >>  5) & 0x3F
_TRAIL_CB =  SWEEP_COLOR        & 0x1F

# Precomputed trail tables (computed once at import, not per frame).
# paint_trail uses the angle-addition identity to compute sin/cos for each
# trail step from just 2 trig calls (sin/cos of az), replacing 80 calls.
_TRAIL_STEPS   = int(TRAIL_DEG / TRAIL_STEP)
_TRAIL_ALPHA   = [int(((i + 1) / _TRAIL_STEPS) ** 2 * 180) for i in range(_TRAIL_STEPS)]
_TRAIL_REL_COS = [math.cos(math.radians(-TRAIL_DEG + i * TRAIL_STEP)) for i in range(_TRAIL_STEPS)]
_TRAIL_REL_SIN = [math.sin(math.radians(-TRAIL_DEG + i * TRAIL_STEP)) for i in range(_TRAIL_STEPS)]


class Sweep:
    def __init__(self, size=240):
        self.size = size
        self.cx = size // 2
        self.cy = size // 2
        self.R = size // 2 - 1            # keeps every plotted pixel in-bounds
        self.fb = bytearray(size * size * 2)
        self._fbmv = memoryview(self.fb)         # zero-copy source for band blit
        # Line pixel offsets stored as o//2 in little-endian uint16 pairs (o always
        # even, max o//2 = 57599 < 65536), same format as the trail buffer so the
        # viper line loop can record them with ptr8 (ptr32+array('i') is unreliable).
        self._line_px = bytearray(2 * _MAX_LINE_PX)
        self._line_n = 0                 # number of valid entries in _line_px
        # pixel offsets stored as half-values (o//2) in uint16 little-endian pairs;
        # o is always even and max o//2 = 57599 < 65536, so 2 bytes per entry suffice.
        self._trail_px    = bytearray(2 * _MAX_TRAIL_PX)
        self._trail_saved = bytearray(2 * _MAX_TRAIL_PX)  # pre-blend fb values
        self._trail_n = 0
        # Per-step direction vectors for the batched viper: (sa_fp+2048, ca_fp+2048)
        # as little-endian uint16 pairs (4 bytes/step). The +2048 bias keeps the
        # signed 11-bit fixed-point value in uint16 range; the viper subtracts it.
        self._trail_dirs  = bytearray(4 * _TRAIL_STEPS)
        # Alpha ramp as a bytearray so the viper can index it (max value 180 < 256).
        self._trail_alpha = bytearray(_TRAIL_ALPHA)

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
        # Native float prep, then a viper integer loop does the per-pixel coverage.
        # Walk the major axis (x if |cos|>=|sin|, else y); at each step the minor-axis
        # line center is mbase + slope*i. pscale (perpendicular normalizer) needs no
        # sqrt: it is exactly |cos| for an x-major line and |sin| for a y-major one,
        # since 1/sqrt(1+(sa/ca)^2) = |ca|. Prep is stashed on self for the viper
        # (keeps its arg count low, the pattern this codebase relies on).
        a = math.radians(deg)
        ca = math.cos(a)
        sa = math.sin(a)
        R = self.R
        hw = SWEEP_HALFWIDTH
        if abs(ca) >= abs(sa):                       # x-major
            self._aa_major = 1
            self._aa_base  = self.cx
            mbase = self.cy
            self._aa_sgn   = 1 if ca >= 0 else -1
            self._aa_steps = int(abs(R * ca))
            slope  = sa / ca
            pscale = abs(ca)
        else:                                        # y-major
            self._aa_major = 0
            self._aa_base  = self.cy
            mbase = self.cx
            self._aa_sgn   = 1 if sa >= 0 else -1
            self._aa_steps = int(abs(R * sa))
            slope  = ca / sa
            pscale = abs(sa)
        reach = (hw + 0.5) / pscale + 1.0
        self._aa_mbase_fp = mbase << 16             # minor-axis line center, fp16
        self._aa_slope_fp = int(slope * 65536)      # minor per major step, fp16
        self._aa_reach    = int(reach) + 1
        self._aa_p8       = int(pscale * 256)        # pscale, fp8
        self._aa_color    = color
        self._aa_line_viper()

    @micropython.viper
    def _aa_line_viper(self):
        # Per-pixel coverage in pure integer math. Coverage scaled to the 0..256
        # alpha range: av = C0 - perp_distance*256, with perp_distance = |mn - m|
        # * pscale. m is fp16; the distance is dropped to fp8 before multiplying by
        # pscale (fp8) so the product stays inside 32-bit signed. Touched offsets are
        # recorded as o//2 in LE uint16 pairs for restore_line().
        fb  = ptr8(self.fb)
        px  = ptr8(self._line_px)
        n   = int(self._line_n)
        cap = int(_MAX_LINE_PX)
        sz  = int(self.size)
        major_x  = int(self._aa_major)
        base     = int(self._aa_base)
        mbase_fp = int(self._aa_mbase_fp)
        slope_fp = int(self._aa_slope_fp)
        sgn      = int(self._aa_sgn)
        steps    = int(self._aa_steps)
        reach_i  = int(self._aa_reach)
        P8       = int(self._aa_p8)
        C0       = int(_AA_C0)
        color = int(self._aa_color)
        chi = color >> 8
        clo = color & 0xFF
        cr  = (color >> 11) & 0x1F
        cg  = (color >>  5) & 0x3F
        cb  =  color        & 0x1F
        for i in range(steps + 1):
            si  = sgn * i
            maj = base + si
            m_fp = mbase_fp + slope_fp * si
            mi  = m_fp >> 16
            mn  = mi - reach_i
            mnend = mi + reach_i
            while mn <= mnend:
                if mn >= 0:
                    if mn < sz:
                        d = (mn << 16) - m_fp
                        if d < 0:
                            d = -d
                        av = C0 - (((d >> 8) * P8) >> 8)
                        if av > 0:
                            if major_x != 0:
                                o = (mn * sz + maj) * 2
                            else:
                                o = (maj * sz + mn) * 2
                            if av >= 256:
                                fb[o]     = chi
                                fb[o + 1] = clo
                            else:
                                ia = 256 - av
                                bg = (fb[o] << 8) | fb[o + 1]
                                rr = (cr * av + ((bg >> 11) & 0x1F) * ia) >> 8
                                gg = (cg * av + ((bg >>  5) & 0x3F) * ia) >> 8
                                bb = (cb * av + ( bg        & 0x1F) * ia) >> 8
                                v  = (rr << 11) | (gg << 5) | bb
                                fb[o]     = v >> 8
                                fb[o + 1] = v & 0xFF
                            if n < cap:
                                half = o >> 1
                                px[n * 2]     = half & 0xFF
                                px[n * 2 + 1] = half >> 8
                                n += 1
                mn += 1
        self._line_n = n

    @micropython.viper
    def _blend_trail_all_viper(self):
        # Paint every trail radial in one pass. The outer loop walks the per-step
        # direction vectors packed into self._trail_dirs by paint_trail; the inner
        # loop blends SWEEP_COLOR * alpha + fb * (1-alpha) along each radial, saving
        # pre-blend fb values so restore_trail() can undo exactly without src.
        # r=0 (center) skipped: all radials converge there and would double-save.
        # Offsets stored as o//2 in little-endian uint16 pairs (o is always even,
        # max o//2 = 57599 < 65536) so ptr8 suffices for _trail_px.
        # Doing all steps in one viper call avoids ~40 native->viper transitions.
        fb   = ptr8(self.fb)
        sv   = ptr8(self._trail_saved)
        px   = ptr8(self._trail_px)
        dirs = ptr8(self._trail_dirs)
        alph = ptr8(self._trail_alpha)
        n    = 0
        cap  = int(_MAX_TRAIL_PX)
        cx   = int(self.cx)
        cy   = int(self.cy)
        sz   = int(self.size)
        R    = int(self.R)
        cr   = int(_TRAIL_CR)
        cg   = int(_TRAIL_CG)
        cb   = int(_TRAIL_CB)
        steps = int(_TRAIL_STEPS)
        for s in range(steps):
            sa_fp = (dirs[s * 4]     | (dirs[s * 4 + 1] << 8)) - 2048
            ca_fp = (dirs[s * 4 + 2] | (dirs[s * 4 + 3] << 8)) - 2048
            alpha256 = alph[s]
            ia = 256 - alpha256
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

    @micropython.native
    def paint_trail(self, az):
        # Pack each step's direction vector using the angle-addition identity
        # sin(az+rel) = sin(az)cos(rel) + cos(az)sin(rel) (2 trig calls total), then
        # hand the whole batch to a single viper call. The +2048 bias keeps the
        # signed 11-bit fixed-point value in uint16 range; the viper subtracts it.
        a = math.radians(az)
        ca = math.cos(a)
        sa = math.sin(a)
        dirs = self._trail_dirs
        for i in range(_TRAIL_STEPS):
            rc = _TRAIL_REL_COS[i]
            rs = _TRAIL_REL_SIN[i]
            sav = int((sa * rc + ca * rs) * 2048) + 2048
            cav = int((ca * rc - sa * rs) * 2048) + 2048
            dirs[i * 4]     = sav & 0xFF
            dirs[i * 4 + 1] = (sav >> 8) & 0xFF
            dirs[i * 4 + 2] = cav & 0xFF
            dirs[i * 4 + 3] = (cav >> 8) & 0xFF
        self._blend_trail_all_viper()

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
                o = (px[i * 2] | (px[i * 2 + 1] << 8)) << 1
                fb[o] = 0
                fb[o + 1] = 0
        else:
            for i in range(n):
                o = (px[i * 2] | (px[i * 2 + 1] << 8)) << 1
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
