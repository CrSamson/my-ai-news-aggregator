"""tools/make_pwa_icons.py — generate Brevio PWA icons.

Writes four PNGs into mobile/public/icons/:
  - icon-192.png            (manifest entry, Chrome install prompt)
  - icon-512.png            (manifest entry, Android home-screen)
  - icon-maskable-512.png   (adaptive icons on Android — has a 20% safe zone
                             around the glyph so the OS can crop a circle / squircle
                             without clipping the B)
  - apple-touch-icon-180.png (iOS Safari "Add to Home Screen")

Design: full-bleed peach (#EE9970) background, cream (#FAF5EE) serif "B".
Georgia Bold from C:\\Windows\\Fonts\\ is used at generate time — visually
indistinguishable from Lora Bold at icon sizes for a single capital letter.
Run from repo root: `python tools/make_pwa_icons.py`.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT       = Path(__file__).resolve().parent.parent
OUT_DIR    = ROOT / "mobile" / "public" / "icons"
FONT_PATH  = Path("C:/Windows/Fonts/georgiab.ttf")   # Georgia Bold

PEACH = (0xEE, 0x99, 0x70, 0xFF)
CREAM = (0xFA, 0xF5, 0xEE, 0xFF)

GLYPH = "B"


def render_icon(size: int, glyph_fraction: float = 0.72) -> Image.Image:
    """Render a square icon: peach background + cream letter.

    glyph_fraction controls how tall the letter is relative to the canvas.
    0.72 fills the canvas tightly (good for standard icons).
    0.55 leaves room for Android's adaptive-icon mask (use for maskable).
    """
    img  = Image.new("RGBA", (size, size), PEACH)
    draw = ImageDraw.Draw(img)

    font_px = int(size * glyph_fraction)
    font    = ImageFont.truetype(str(FONT_PATH), font_px)

    # Use textbbox for accurate centering — getsize is off by a few px
    # because of ascender/descender padding in the font metrics.
    bbox = draw.textbbox((0, 0), GLYPH, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) // 2 - bbox[0]
    y = (size - text_h) // 2 - bbox[1]

    draw.text((x, y), GLYPH, font=font, fill=CREAM)
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Standard PWA icons — full-bleed glyph.
    render_icon(192, glyph_fraction=0.72).save(OUT_DIR / "icon-192.png", optimize=True)
    render_icon(512, glyph_fraction=0.72).save(OUT_DIR / "icon-512.png", optimize=True)

    # Maskable: smaller glyph so the OS adaptive-icon mask never crops it.
    # PWA spec says safe zone = 80% of canvas; we render at 55% for comfort.
    render_icon(512, glyph_fraction=0.55).save(OUT_DIR / "icon-maskable-512.png", optimize=True)

    # iOS Safari "Add to Home Screen" uses 180×180 by convention. iOS adds
    # rounded corners automatically, so the source can stay square.
    render_icon(180, glyph_fraction=0.72).save(OUT_DIR / "apple-touch-icon-180.png", optimize=True)

    print(f"Wrote 4 icons to {OUT_DIR}")


if __name__ == "__main__":
    main()
