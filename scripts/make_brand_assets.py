"""Draw Leadroom's icons from the mark's own vector paths, in the Field Book palette.

    python scripts/make_brand_assets.py

The mark's shape is fixed; its colours follow the app (frontend/src/styles/tokens.css):
a bookcloth-green tile, the upright stroke in survey-paper white and the foot in the
rail's light ink blue. Writes:

    assets/leadroom-icon.png / .ico / .svg   app icon (also used by the READMEs)
    assets/leadroom-setup.ico                the same tile with a download badge
    assets/leadroom-mark-color.png           the two-colour mark on transparency
    frontend/public/favicon.svg              browser tab icon
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

CLOTH = (31, 58, 48)        # --cloth #1F3A30
PAPER = (244, 247, 244)     # --cloth-accent #F4F7F4
INK_LIGHT = (143, 174, 255)  # rail mark foot #8FAEFF
ACTION = (31, 79, 224)      # --action #1F4FE0

FOOT = (
    "M415.38,3000h152.9l1385.55-.04c270.54-28.62,361.3-80.29,538.28-327.18l166.88-238.83,341.01-505.81"
    "-1084.23,1.64c-262.22-15.72-437.21,159.07-486.87,218.55l-224.4,233.16-394.07,396.81c-63.74,58.09"
    "-112.94,104.57-185.29,149.6C552.76,2972.97,488.95,2999.28,415.38,3000Z"
)
STEM = (
    "M0,2584.62c0-56.09,0-99.06,0-152.9l.04-1385.55c28.62-270.54,80.29-361.3,327.18-538.28l238.83-166.88"
    "L1071.86,0l-1.64,1084.23c15.72,262.22-159.07,437.21-218.55,486.87l-233.16,224.4-396.81,394.07"
    "c-58.09,63.74-104.57,112.94-149.6,185.29C27.03,2447.24.72,2511.05,0,2584.62Z"
)
MARK_SIZE = 3000.0


def _tokens(d: str):
    for match in re.finditer(r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?", d):
        yield match.group(0)


def flatten(d: str, steps: int = 24) -> list[tuple[float, float]]:
    """The path's outline as points (supports M, L, H, V, C, Z, absolute and relative)."""
    tokens = list(_tokens(d))
    points: list[tuple[float, float]] = []
    x = y = 0.0
    i = 0
    command = ""

    def number() -> float:
        nonlocal i
        value = float(tokens[i])
        i += 1
        return value

    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
            if command in "Zz":
                continue
        relative = command.islower()
        kind = command.upper()
        if kind == "M" or kind == "L":
            nx, ny = number(), number()
            x, y = (x + nx, y + ny) if relative else (nx, ny)
            points.append((x, y))
            if kind == "M":
                command = "l" if relative else "L"
        elif kind == "H":
            nx = number()
            x = x + nx if relative else nx
            points.append((x, y))
        elif kind == "V":
            ny = number()
            y = y + ny if relative else ny
            points.append((x, y))
        elif kind == "C":
            c1x, c1y, c2x, c2y, ex, ey = (number() for _ in range(6))
            if relative:
                c1x, c1y, c2x, c2y, ex, ey = x + c1x, y + c1y, x + c2x, y + c2y, x + ex, y + ey
            for step in range(1, steps + 1):
                t = step / steps
                u = 1 - t
                px = u**3 * x + 3 * u * u * t * c1x + 3 * u * t * t * c2x + t**3 * ex
                py = u**3 * y + 3 * u * u * t * c1y + 3 * u * t * t * c2y + t**3 * ey
                points.append((px, py))
            x, y = ex, ey
        else:
            raise ValueError(f"unsupported path command {command}")
    return points


def draw_mark(size: int, box: tuple[float, float, float], stem=PAPER, foot=INK_LIGHT, supersample: int = 4) -> Image.Image:
    """The two-colour mark on transparency; box = (left, top, side) in output pixels."""
    big = size * supersample
    layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    left, top, side = (value * supersample for value in box)
    scale = side / MARK_SIZE
    for path, colour in ((STEM, stem), (FOOT, foot)):
        outline = [(left + px * scale, top + py * scale) for px, py in flatten(path)]
        draw.polygon(outline, fill=colour + (255,))
    return layer.resize((size, size), Image.LANCZOS)


def tile(size: int, supersample: int = 4) -> Image.Image:
    """The app icon: a bookcloth tile with the mark."""
    big = size * supersample
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    inset = round(big * 0.035)
    radius = round(big * 0.22)
    draw.rounded_rectangle((inset, inset, big - inset - 1, big - inset - 1), radius=radius, fill=CLOTH + (255,))
    image = image.resize((size, size), Image.LANCZOS)
    side = size * 0.58
    image.alpha_composite(draw_mark(size, ((size - side) / 2 + size * 0.01, (size - side) / 2, side)))
    return image


def setup_tile(size: int) -> Image.Image:
    """The Setup icon: the app tile with an ink-blue download badge."""
    image = tile(size)
    ss = 4
    big = size * ss
    badge = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    r = big * 0.21
    cx, cy = big - r - big * 0.02, r + big * 0.02
    draw.ellipse((cx - r - big * 0.025, cy - r - big * 0.025, cx + r + big * 0.025, cy + r + big * 0.025), fill=PAPER + (255,))
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ACTION + (255,))
    w = big * 0.035
    draw.line((cx, cy - r * 0.5, cx, cy + r * 0.32), fill=(255, 255, 255, 255), width=round(w))
    draw.polygon([(cx - r * 0.42, cy + r * 0.02), (cx + r * 0.42, cy + r * 0.02), (cx, cy + r * 0.5)], fill=(255, 255, 255, 255))
    draw.line((cx - r * 0.5, cy + r * 0.66, cx + r * 0.5, cy + r * 0.66), fill=(255, 255, 255, 255), width=round(w))
    image.alpha_composite(badge.resize((size, size), Image.LANCZOS))
    return image


def icon_svg() -> str:
    hex_ = lambda c: "#%02X%02X%02X" % c  # noqa: E731
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">\n'
        f'  <rect x="9" y="9" width="238" height="238" rx="56" fill="{hex_(CLOTH)}"/>\n'
        f'  <g transform="translate(55.5 53.6) scale(0.04949)">\n'
        f'    <path fill="{hex_(PAPER)}" d="{STEM}"/>\n'
        f'    <path fill="{hex_(INK_LIGHT)}" d="{FOOT}"/>\n'
        "  </g>\n</svg>\n"
    )


def main() -> None:
    big = tile(1024)
    big.save(ASSETS / "leadroom-icon.png", optimize=True)
    sizes = [(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)]
    tile(256).save(ASSETS / "leadroom-icon.ico", sizes=sizes)
    setup_tile(256).save(ASSETS / "leadroom-setup.ico", sizes=sizes)
    draw_mark(1106, (0, 0, 1106)).save(ASSETS / "leadroom-mark-color.png", optimize=True)
    svg = icon_svg()
    (ASSETS / "leadroom-icon.svg").write_text(svg, encoding="utf-8")
    (ROOT / "frontend" / "public" / "favicon.svg").write_text(svg, encoding="utf-8")
    print("Wrote app icon, Setup icon, mark and favicon in the Field Book palette.")


if __name__ == "__main__":
    main()
