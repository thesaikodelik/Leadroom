"""Draw the Setup wizard's side panel and header images in the Field Book palette.

    python scripts/make_installer_images.py

Writes installer/images/wizard-{large,small}-{100,125,150,200}.bmp. Each image is
drawn at four times its size and scaled down, so edges stay smooth at every DPI.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "installer" / "images"
FONTS = Path(r"C:\Windows\Fonts")

import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_brand_assets import CLOTH, INK_LIGHT, PAPER, draw_mark, tile  # noqa: E402

SCALES = {100: 1.0, 125: 1.25, 150: 1.5, 200: 2.0}
LARGE = (164, 314)
SMALL = 55
SUPER = 4
EV_4 = (47, 97, 81)  # --ev-4, the traverse line


def font(name: str, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), max(1, round(size)))


def cloth(size: tuple[int, int]) -> Image.Image:
    """The rail's bookcloth green. The app's fine weave turns into stripes at this size, so it stays flat."""
    return Image.new("RGBA", size, CLOTH + (255,))


def traverse(draw: ImageDraw.ImageDraw, left: float, y: float, width: float, u: float) -> None:
    """Four survey stations on a line: the Field Book's signature, small."""
    draw.line((left, y, left + width, y), fill=PAPER + (90,), width=max(1, round(1.4 * u)))
    for index in range(4):
        cx = left + width * index / 3
        r = 4.2 * u
        points = [(cx, y - r), (cx + r, y + r * 0.8), (cx - r, y + r * 0.8)]
        fill = INK_LIGHT if index == 3 else PAPER
        draw.polygon(points, fill=fill + (255,))


def large(scale: float) -> Image.Image:
    w, h = round(LARGE[0] * scale), round(LARGE[1] * scale)
    W, H = w * SUPER, h * SUPER
    u = W / LARGE[0]  # one design unit at this size

    img = cloth((W, H))
    # A large, faint copy of the mark running off the bottom right corner.
    ghost = draw_mark(round(230 * u), (0, 0, round(230 * u)), stem=PAPER, foot=PAPER, supersample=1)
    ghost.putalpha(ghost.getchannel("A").point(lambda a: round(a * 0.06)))
    img.alpha_composite(ghost, (round(W - 150 * u), round(H - 175 * u)))
    # The edge where the panel meets the page.
    edge = Image.new("RGBA", (max(1, round(0.6 * u)), H), (0, 0, 0, 60))
    img.alpha_composite(edge, (W - edge.width, 0))

    left = round(20 * u)
    side = round(40 * u)
    img.alpha_composite(draw_mark(side, (0, 0, side), supersample=1), (left, round(46 * u)))

    draw = ImageDraw.Draw(img)
    draw.text((left - round(1 * u), round(98 * u)), "Leadroom", font=font("segoeuib.ttf", 22 * u), fill=(255, 255, 255, 255))
    traverse(draw, left + 4 * u, round(136 * u), 52 * u, u)

    body = font("segoeui.ttf", 10.5 * u)
    y = round(152 * u)
    for line in ["Find local businesses", "and reach out carefully,", "from your own PC."]:
        draw.text((left, y), line, font=body, fill=PAPER + (215,))
        y += round(15 * u)
    return img.convert("RGB").resize((w, h), Image.LANCZOS)


def small(scale: float) -> Image.Image:
    s = round(SMALL * scale)
    canvas = Image.new("RGBA", (s, s), (255, 255, 255, 255))
    canvas.alpha_composite(tile(s))
    return canvas.convert("RGB")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for percent, scale in SCALES.items():
        large(scale).save(OUT / f"wizard-large-{percent}.bmp")
        small(scale).save(OUT / f"wizard-small-{percent}.bmp")
    print(f"Wrote {len(SCALES) * 2} images to {OUT}")


if __name__ == "__main__":
    main()
