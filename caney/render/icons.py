"""
PWA icons, generated rather than committed as binaries. §42.

stdlib only (zlib + struct), like everything else here. A flat ground with the site's
wave mark, at the two sizes the manifest asks for. Deterministic, so a rebuild does not
churn the file.
"""
import struct
import zlib

BG = (13, 20, 28)        # --bg dark
FG = (90, 169, 255)      # --accent dark
FG2 = (23, 134, 74)      # --go


def _png(width, height, pixels):
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(row) for row in pixels)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def icon(size):
    """A wave over a dark ground — the same 🌊 idea as the site emoji, drawn in pixels."""
    import math
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            u, v = x / size, y / size
            # two sine bands, thick enough to read at 48px
            c = BG
            for k, (amp, off, col) in enumerate(((0.055, 0.42, FG), (0.045, 0.62, FG2))):
                band = off + amp * math.sin((u * 2.6 + k * 0.5) * math.pi * 2)
                if abs(v - band) < 0.075:
                    c = col
            # rounded corners
            r = 0.11
            dx = min(u, 1 - u) / r
            dy = min(v, 1 - v) / r
            if dx < 1 and dy < 1 and (1 - dx) ** 2 + (1 - dy) ** 2 > 1:
                c = (0, 0, 0)
            row.extend(c)
        rows.append(row)
    return _png(size, size, rows)


def write(out_dir):
    import os
    made = []
    for s in (192, 512):
        p = os.path.join(out_dir, "icon-%d.png" % s)
        with open(p, "wb") as fh:
            fh.write(icon(s))
        made.append(p)
    return made
