#!/usr/bin/env python3
"""Génère l'icône PNG multi-résolution pour ROCmFP4 Manager."""

import struct
import zlib
from pathlib import Path


def create_png(width, height, pixels):
    """Crée un fichier PNG à partir de pixels RGBA."""
    # Filter bytes (0 = None for each row)
    raw = b""
    for row in pixels:
        raw += b"\x00" + bytes(row)

    def chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    # IHDR
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    # IDAT
    compressed = zlib.compress(raw)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


def build_icon(size):
    """Génère les pixels RGBA pour l'icône aux dimensions données."""
    pixels = []
    bg = (26, 26, 46, 255)  # #1a1a2e
    chip = (45, 45, 68, 255)  # #2d2d44
    accent = (233, 69, 96, 255)  # #e94560
    white = (255, 255, 255, 255)
    red = (255, 77, 0, 255)  # #ff4d00

    r = size
    margin = int(r * 0.15)
    chip_size = r - 2 * margin

    for y in range(r):
        row = []
        for x in range(r):
            # Background arrondi
            dx = x - r // 2
            dy = y - r // 2
            corner_r = r // 4
            in_bg = (abs(dx) <= r // 2 - corner_r or abs(dy) <= r // 2 - corner_r) or \
                    ((dx - (r // 2 - corner_r)) ** 2 + (dy - (r // 2 - corner_r)) ** 2 <= corner_r ** 2 or
                     (dx + (r // 2 - corner_r)) ** 2 + (dy - (r // 2 - corner_r)) ** 2 <= corner_r ** 2 or
                     (dx - (r // 2 - corner_r)) ** 2 + (dy + (r // 2 - corner_r)) ** 2 <= corner_r ** 2 or
                     (dx + (r // 2 - corner_r)) ** 2 + (dy + (r // 2 - corner_r)) ** 2 <= corner_r ** 2)

            if not in_bg:
                row.append((0, 0, 0, 0))
                continue

            # Chip central
            cx, cy = x - margin, y - margin
            chip_corner = chip_size // 5
            on_chip = (cx >= 0 and cy >= 0 and cx < chip_size and cy < chip_size)

            if not on_chip:
                row.append(bg)
                continue

            # Vérifier si dans le chip arrondi
            in_chip = (abs(cx - chip_size // 2) <= chip_size // 2 - chip_corner or
                       abs(cy - chip_size // 2) <= chip_size // 2 - chip_corner) or \
                      ((cx - chip_corner) ** 2 + (cy - chip_corner) ** 2 <= chip_corner ** 2 or
                       (cx - (chip_size - chip_corner)) ** 2 + (cy - chip_corner) ** 2 <= chip_corner ** 2 or
                       (cx - chip_corner) ** 2 + (cy - (chip_size - chip_corner)) ** 2 <= chip_corner ** 2 or
                       (cx - (chip_size - chip_corner)) ** 2 + (cy - (chip_size - chip_corner)) ** 2 <= chip_corner ** 2)

            if not in_chip:
                row.append(bg)
                continue

            # Bordure du chip (3px)
            stroke = 3
            on_border = (cx < stroke or cx >= chip_size - stroke or
                         cy < stroke or cy >= chip_size - stroke)
            if on_border:
                row.append(red)
                continue

            # Texte FP4
            if size >= 48:
                # Ligne horizontale (simulant le texte FP4)
                center_y = chip_size // 2 - 2
                if abs(cy - center_y) <= 2 and chip_size // 3 < cx < 2 * chip_size // 3:
                    row.append(white)
                    continue

            # Badge ROCmFP4 en bas
            badge_y_start = chip_size - chip_size // 5 - 2
            badge_y_end = chip_size - 2
            if badge_y_start <= cy <= badge_y_end and chip_size // 5 < cx < 4 * chip_size // 5:
                row.append(red)
                continue

            row.append(chip)

        pixels.append(row)
    return pixels


# Générer les icônes 16, 32, 48, 64, 128, 256
sizes = [16, 32, 48, 64, 128, 256]
output_dir = Path(__file__).parent

for s in sizes:
    pixels = build_icon(s)
    png_data = create_png(s, s, pixels)
    path = output_dir / f"icon_{s}.png"
    path.write_bytes(png_data)
    print(f"✅ Generated {path} ({s}x{s})")

print("✅ All icons generated!")
