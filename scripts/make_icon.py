"""Render assets/folio.ico (Windows shortcut icon) to match folio/web/icon.svg. Needs Pillow: pip install pillow"""

from pathlib import Path

from PIL import Image, ImageDraw

S = 1024  # draw large, downsample for crisp small sizes
OUT = Path(__file__).resolve().parent.parent / "assets" / "folio.ico"


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def main():
    k = S / 64  # the SVG is drawn on a 64x64 grid
    grad = Image.new("RGBA", (S, S))
    top, bottom = (0x91, 0x82, 0xFF), (0x3B, 0x82, 0xF6)
    px = grad.load()
    for y in range(S):
        for x in range(S):
            px[x, y] = (*lerp(top, bottom, (x + y) / (2 * S)), 255)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=15 * k, fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(grad, mask=mask)

    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x, y, w, h, a in [(22, 11, 25, 32, 90), (19.5, 15.5, 25, 32, 153), (17, 20, 25, 33, 255)]:
        d.rounded_rectangle([x * k, y * k, (x + w) * k, (y + h) * k], radius=4 * k, fill=(255, 255, 255, a))
    for y, w, a in [(28, 15, 180), (34, 15, 115), (40, 10, 115)]:
        d.rounded_rectangle([22 * k, y * k, (22 + w) * k, (y + 2.6) * k], radius=1.3 * k, fill=(0x6D, 0x5E, 0xFC, a))
    icon = Image.alpha_composite(icon, layer)

    OUT.parent.mkdir(exist_ok=True)
    icon.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.resize((256, 256), Image.LANCZOS).save(OUT.with_suffix(".png"))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
