#!/usr/bin/env python3
"""Generate PageProbe PNG icons (16/48/128) with no third-party dependencies.

A green magnifier glyph (accent #3fb950) on the warm-void background
(#0d0c0a), matching the SQLSage query-console palette. Anti-aliased via a
soft-edged distance field, so no supersampling or PIL is required.

Usage: python3 tools/make_icons.py
"""
import math
import os
import struct
import sys
import zlib

VOID = (13, 12, 10, 255)   # #0d0c0a warm void
ACCENT = (63, 185, 80, 255)  # #3fb950 green


def png_write(path, width, height, rgba):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        c += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return c

    raw = b""
    for y in range(height):
        start = y * width * 4
        raw += b"\x00" + bytes(rgba[start:start + width * 4])
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    with open(path, "wb") as f:
        f.write(png)


def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def clamp01(v):
    return 0.0 if v < 0 else (1.0 if v > 1 else v)


def make_icon(size):
    cx, cy = 0.42 * size, 0.42 * size
    outer = 0.30 * size
    inner = outer - 0.105 * size
    edge = max(1.0, size / 80.0)
    # Handle along the 45-degree line, from the ring edge outward.
    ang = math.radians(45)
    h1 = (cx + outer * math.cos(ang), cy + outer * math.sin(ang))
    h2 = (cx + 0.78 * size * math.cos(ang), cy + 0.78 * size * math.sin(ang))
    hw = 0.10 * size

    rgba = bytearray()
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy)
            ring = clamp01((outer - d) / edge) * clamp01((d - inner) / edge)
            s = seg_dist(x, y, h1[0], h1[1], h2[0], h2[1])
            cov = max(ring, clamp01((hw - s) / edge))
            if cov <= 0:
                rgba += bytes(VOID)
            else:
                r = int(round(VOID[0] + (ACCENT[0] - VOID[0]) * cov))
                g = int(round(VOID[1] + (ACCENT[1] - VOID[1]) * cov))
                b = int(round(VOID[2] + (ACCENT[2] - VOID[2]) * cov))
                rgba += bytes((r, g, b, 255))
    return bytes(rgba)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "icons")
    os.makedirs(out_dir, exist_ok=True)
    for size in (16, 48, 128):
        path = os.path.join(out_dir, "%d.png" % size)
        png_write(path, size, size, make_icon(size))
        print("wrote %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
