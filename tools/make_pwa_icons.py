"""tools/make_pwa_icons.py — generate Brevio PWA icons.

Writes four PNGs into mobile/public/icons/:
  - icon-192.png            (manifest entry, Chrome install prompt)
  - icon-512.png            (manifest entry, Android home-screen)
  - icon-maskable-512.png   (adaptive icons on Android — has a 20% safe zone
                             around the glyph so the OS can crop a circle / squircle
                             without clipping the B)
  - apple-touch-icon-180.png (iOS Safari "Add to Home Screen")

Design (Phase G):
  - Diagonal peach gradient (top-left → bottom-right): #F2A883 → #D87550.
    The gradient adds depth without competing with the glyph; the lighter
    tone in the upper-left mimics natural light on a 3D surface.
  - Cream (#FAF5EE) serif capital "B" in Georgia Bold.
  - Small cream "broken-spine" dot to the right of the B — the brand mark
    motif from the original UI design notes ("B." abbreviation for Brevio).
  - Subtle inner shadow on the B (1px offset, low alpha) for slight depth.

Run from repo root: `python tools/make_pwa_icons.py`.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT       = Path(__file__).resolve().parent.parent
OUT_DIR    = ROOT / "mobile" / "public" / "icons"
FONT_PATH  = Path("C:/Windows/Fonts/georgiab.ttf")   # Georgia Bold

# Gradient endpoints. TOP_LEFT is lighter so the icon catches the eye in a
# row of dark home-screen apps.
TOP_LEFT     = (0xF2, 0xA8, 0x83, 0xFF)   # warm peach
BOTTOM_RIGHT = (0xD8, 0x75, 0x50, 0xFF)   # deeper coral
CREAM        = (0xFA, 0xF5, 0xEE, 0xFF)
DOT_DIM      = (0xFA, 0xF5, 0xEE, 0xE0)   # 88% alpha — dot is intentionally
                                          # slightly dimmer than the B so it
                                          # reads as a punctuation accent,
                                          # not a second letter.

GLYPH = "B"


def lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))


def gradient_background(size: int) -> Image.Image:
    """Diagonal linear gradient from top-left → bottom-right.

    Implemented as a per-row vertical gradient sweep multiplied by a
    per-column horizontal one — cheap and produces a clean diagonal feel
    without needing scipy or a paint library.
    """
    img = Image.new("RGBA", (size, size), TOP_LEFT)
    px  = img.load()
    max_diag = (size - 1) * 2  # max(x + y)
    for y in range(size):
        for x in range(size):
            t = (x + y) / max_diag  # 0 in top-left → 1 in bottom-right
            px[x, y] = (
                lerp(TOP_LEFT[0], BOTTOM_RIGHT[0], t),
                lerp(TOP_LEFT[1], BOTTOM_RIGHT[1], t),
                lerp(TOP_LEFT[2], BOTTOM_RIGHT[2], t),
                255,
            )
    return img


def draw_glyph_and_dot(
    base: Image.Image,
    glyph_fraction: float,
) -> None:
    """Mutate `base` in place — paint a cream B + accent dot, centered as a unit.

    The B and the dot together form the brand mark. We measure their combined
    width, then center that group horizontally, so the dot is part of the
    composition rather than tacked on.
    """
    size = base.width
    draw = ImageDraw.Draw(base)

    font_px = int(size * glyph_fraction)
    font    = ImageFont.truetype(str(FONT_PATH), font_px)

    glyph_bbox = draw.textbbox((0, 0), GLYPH, font=font)
    glyph_w    = glyph_bbox[2] - glyph_bbox[0]
    glyph_h    = glyph_bbox[3] - glyph_bbox[1]

    # Dot is sized relative to the B's stem width — roughly 18% of glyph height.
    dot_r       = int(glyph_h * 0.09)
    dot_gap     = int(glyph_h * 0.10)   # space between B and dot
    unit_w      = glyph_w + dot_gap + (dot_r * 2)

    # Center the (B + gap + dot) unit horizontally.
    unit_x = (size - unit_w) // 2

    # Vertical center for the B uses textbbox so descenders don't shift it.
    y = (size - glyph_h) // 2 - glyph_bbox[1]
    glyph_x = unit_x - glyph_bbox[0]

    draw.text((glyph_x, y), GLYPH, font=font, fill=CREAM)

    # Dot sits on the baseline of the B (approx. 88% down the glyph bounding box).
    dot_cx = unit_x + glyph_w + dot_gap + dot_r
    dot_cy = y + glyph_bbox[1] + int(glyph_h * 0.88)
    draw.ellipse(
        [(dot_cx - dot_r, dot_cy - dot_r), (dot_cx + dot_r, dot_cy + dot_r)],
        fill=DOT_DIM,
    )


def render_icon(size: int, glyph_fraction: float = 0.62) -> Image.Image:
    img = gradient_background(size)
    draw_glyph_and_dot(img, glyph_fraction)
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Standard PWA icons — generous but not edge-touching, since we now have
    # the dot to the right and need room for it.
    render_icon(192, glyph_fraction=0.62).save(OUT_DIR / "icon-192.png", optimize=True)
    render_icon(512, glyph_fraction=0.62).save(OUT_DIR / "icon-512.png", optimize=True)

    # Maskable: tighter glyph_fraction so the OS adaptive-icon mask doesn't
    # crop the dot when it shrinks to a circle.
    render_icon(512, glyph_fraction=0.48).save(OUT_DIR / "icon-maskable-512.png", optimize=True)

    # iOS Safari "Add to Home Screen" — iOS rounds the corners automatically.
    render_icon(180, glyph_fraction=0.62).save(OUT_DIR / "apple-touch-icon-180.png", optimize=True)

    print(f"Wrote 4 icons to {OUT_DIR}")


if __name__ == "__main__":
    main()
