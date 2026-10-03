"""Generate placeholder brand images (purple rounded square with a white "V").

Requires Pillow. Run from the repo root: python scripts/gen_brand.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "brand"
PURPLE = (94, 39, 165, 255)
WHITE = (255, 255, 255, 255)


def draw_icon(size: int) -> Image.Image:
    scale = 4  # supersample for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.2), fill=PURPLE)
    # "V" as a polygon: outer left, outer right, then the inner notch.
    top, bottom = s * 0.22, s * 0.80
    stroke = s * 0.15
    left, right, mid = s * 0.20, s * 0.80, s * 0.50
    draw.polygon(
        [
            (left, top),
            (left + stroke, top),
            (mid, bottom - stroke * 1.15),
            (right - stroke, top),
            (right, top),
            (mid + stroke * 0.55, bottom),
            (mid - stroke * 0.55, bottom),
        ],
        fill=WHITE,
    )
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    draw_icon(256).save(OUT / "icon.png", optimize=True)
    draw_icon(512).save(OUT / "icon@2x.png", optimize=True)
    draw_icon(256).save(OUT / "logo.png", optimize=True)


if __name__ == "__main__":
    main()
