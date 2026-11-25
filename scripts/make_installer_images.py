"""Draw the Setup wizard's side panel and header images from the Leadroom mark.

    python scripts/make_installer_images.py

Writes installer/images/wizard-{large,small}-{100,125,150,200}.bmp. Each image is
drawn at four times its size and scaled down, so edges stay smooth at every DPI.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MARK = ROOT / "assets" / "leadroom-mark-color.png"
OUT = ROOT / "installer" / "images"
FONTS = Path(r"C:\Windows\Fonts")

SCALES = {100: 1.0, 125: 1.25, 150: 1.5, 200: 2.0}
LARGE = (164, 314)
SMALL = 55
SUPER = 4

# The mark's own gradient, from deep navy to cyan.
NAVY = (4, 10, 58)
INK = (6, 24, 120)
BLUE = (4, 56, 216)
SKY = (10, 142, 240)
CYAN = (0, 245, 214)


def font(name: str, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), max(1, round(size)))


def white_mark(size: int, opacity: float = 1.0) -> Image.Image:
    """The mark's shape in white, keeping its anti-aliased edge."""
    alpha = Image.open(MARK).getchannel("A").resize((size, size), Image.LANCZOS)
    if opacity < 1:
        alpha = alpha.point(lambda a: round(a * opacity))
    mark = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    mark.putalpha(alpha)
    return mark


def gradient(size: tuple[int, int], stops: list[tuple[float, tuple[int, int, int]]]) -> Image.Image:
    """A diagonal gradient from the top left to the bottom right."""
    w, h = size
    ramp = Image.new("RGB", (512, 1))
    for x in range(512):
        t = x / 511
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0) if t1 > t0 else 0
                ramp.putpixel((x, 0), tuple(round(a + (b - a) * k) for a, b in zip(c0, c1)))
                break
    # Stretch the ramp over the diagonal, then rotate it into place.
    side = int((w * w + h * h) ** 0.5) + 2
    angle = -_degrees(w, h)
    big = ramp.resize((side, side)).rotate(angle, resample=Image.BICUBIC, expand=False)
    return big.crop(((side - w) // 2, (side - h) // 2, (side - w) // 2 + w, (side - h) // 2 + h))


def _degrees(w: int, h: int) -> float:
    import math

    return math.degrees(math.atan2(h, w))


def glow(size: tuple[int, int], centre: tuple[float, float], radius: float, colour, strength: int) -> Image.Image:
    layer = Image.new("RGBA", size, colour + (0,))
    mask = Image.new("L", size, 0)
    cx, cy = centre
    ImageDraw.Draw(mask).ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=strength)
    layer.putalpha(mask.filter(ImageFilter.GaussianBlur(radius * 0.55)))
    return layer


def large(scale: float) -> Image.Image:
    w, h = round(LARGE[0] * scale), round(LARGE[1] * scale)
    W, H = w * SUPER, h * SUPER
    u = W / LARGE[0]  # one design unit at this size

    img = gradient((W, H), [(0.0, NAVY), (0.45, INK), (0.8, BLUE), (1.0, SKY)]).convert("RGBA")
    img.alpha_composite(glow((W, H), (W * 0.95, H * 0.98), 120 * u, CYAN, 120))
    img.alpha_composite(glow((W, H), (W * 0.05, H * 0.05), 90 * u, SKY, 50))

    # A large, faint copy of the mark running off the bottom right corner.
    ghost = white_mark(round(230 * u), 0.07)
    img.alpha_composite(ghost, (round(W - 150 * u), round(H - 175 * u)))

    # Thin highlight line on the right edge, where the panel meets the page.
    edge = Image.new("RGBA", (max(1, round(0.5 * u)), H), (255, 255, 255, 40))
    img.alpha_composite(edge, (W - edge.width, 0))

    left = round(20 * u)
    mark = white_mark(round(40 * u))
    img.alpha_composite(mark, (left, round(46 * u)))

    draw = ImageDraw.Draw(img)
    title = font("segoeuib.ttf", 22 * u)
    draw.text((left - round(1 * u), round(98 * u)), "Leadroom", font=title, fill=(255, 255, 255, 255))

    accent_y = round(132 * u)
    draw.rounded_rectangle(
        (left, accent_y, left + round(24 * u), accent_y + round(2.5 * u)),
        radius=round(1.25 * u),
        fill=CYAN + (255,),
    )

    body = font("segoeui.ttf", 10.5 * u)
    lines = ["Find local businesses", "and reach out carefully,", "from your own PC."]
    y = round(146 * u)
    for line in lines:
        draw.text((left, y), line, font=body, fill=(255, 255, 255, 205))
        y += round(15 * u)

    return img.convert("RGB").resize((w, h), Image.LANCZOS)


def small(scale: float) -> Image.Image:
    s = round(SMALL * scale)
    S = s * SUPER
    canvas = Image.new("RGBA", (S, S), (255, 255, 255, 255))

    pad = round(S * 0.08)
    tile_size = S - 2 * pad
    tile = gradient((tile_size, tile_size), [(0.0, INK), (0.55, BLUE), (1.0, SKY)]).convert("RGBA")
    tile.alpha_composite(glow((tile_size, tile_size), (tile_size, tile_size), tile_size * 0.6, CYAN, 110))
    mask = Image.new("L", (tile_size, tile_size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, tile_size - 1, tile_size - 1), radius=round(tile_size * 0.24), fill=255)
    tile.putalpha(ImageChops.multiply(tile.getchannel("A"), mask))
    canvas.alpha_composite(tile, (pad, pad))

    m = round(tile_size * 0.56)
    canvas.alpha_composite(white_mark(m), (pad + (tile_size - m) // 2, pad + (tile_size - m) // 2))
    return canvas.convert("RGB").resize((s, s), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for percent, scale in SCALES.items():
        large(scale).save(OUT / f"wizard-large-{percent}.bmp")
        small(scale).save(OUT / f"wizard-small-{percent}.bmp")
    print(f"Wrote {len(SCALES) * 2} images to {OUT}")


if __name__ == "__main__":
    main()
