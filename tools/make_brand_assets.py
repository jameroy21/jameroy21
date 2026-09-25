#!/usr/bin/env python3
"""Generate Clear Price brand assets (app icons + social share image).

Run from the repo root with Pillow installed:
    .venv/bin/python tools/make_brand_assets.py

Writes into frontend/public/:
    icons/icon-192.png            Android / PWA
    icons/icon-512.png            Android / PWA / splash
    icons/icon-maskable-512.png   Android adaptive icon (full bleed, safe zone)
    icons/apple-touch-icon.png    iOS home screen (180, no transparency)
    icons/favicon-32.png          browser tab
    og-image.png                  1200x630 link preview (WhatsApp, X, iMessage...)

The mark: a white price tag, tilted, with a % on it — legible at 32px.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "frontend" / "public"
ICONS = PUBLIC / "icons"

BRAND = (11, 78, 162)  # #0b4ea2
BRAND_DARK = (7, 58, 121)  # #073a79
WHITE = (255, 255, 255)
INK = (11, 18, 32)  # #0b1220
SAVED_GREEN = (15, 123, 63)  # #0f7b3f
PALE = (207, 224, 247)  # #cfe0f7

BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

SS = 4  # supersample factor: draw big, shrink down -> smooth edges


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def brand_background(size: int) -> Image.Image:
    """Vertical gradient of the brand blue — depth without any hard seams."""
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(size - 1, 1)
        grad.putpixel(
            (0, y),
            tuple(
                int(round(BRAND_DARK[i] + (BRAND[i] - BRAND_DARK[i]) * t)) for i in range(3)
            ),
        )
    return grad.resize((size, size), Image.BILINEAR)


def draw_tag(layer: Image.Image, size: int, *, tag_w_ratio: float, tag_h_ratio: float) -> None:
    """A white sale tag with a hole punched through it and a % in the middle."""
    d = ImageDraw.Draw(layer)
    cx = cy = size / 2

    tag_w = size * tag_w_ratio
    tag_h = size * tag_h_ratio
    left, top = cx - tag_w / 2, cy - tag_h / 2
    right, bottom = cx + tag_w / 2, cy + tag_h / 2
    d.rounded_rectangle(
        [left, top, right, bottom], radius=tag_h * 0.24, fill=WHITE
    )

    # Punch the string hole right through the tag (transparent, not a dot).
    hole_r = tag_h * 0.085
    hole_x = left + tag_h * 0.34
    hole = Image.new("L", (size, size), 0)
    ImageDraw.Draw(hole).ellipse(
        [hole_x - hole_r, cy - hole_r, hole_x + hole_r, cy + hole_r], fill=255
    )
    layer.putalpha(
        Image.composite(Image.new("L", (size, size), 0), layer.getchannel("A"), hole)
    )

    # A real % glyph: correct proportions, no self-intersections.
    percent = font(BOLD, int(tag_h * 0.62))
    glyph = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glyph)
    box = gd.textbbox((0, 0), "%", font=percent)
    gd.text(
        (cx * 1.22 - (box[2] - box[0]) / 2 - box[0], cy - (box[3] - box[1]) / 2 - box[1]),
        "%",
        font=percent,
        fill=BRAND,
    )
    layer.alpha_composite(glyph)


def make_icon(size: int, *, maskable: bool = False) -> Image.Image:
    """Square app icon. maskable=True keeps everything inside Android's safe zone."""
    big = size * SS
    icon = brand_background(big).convert("RGBA")

    tag_layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    # Maskable icons get cropped to a circle by the launcher: keep the tag smaller.
    draw_tag(
        tag_layer,
        big,
        tag_w_ratio=0.48 if maskable else 0.60,
        tag_h_ratio=0.34 if maskable else 0.43,
    )
    tag_layer = tag_layer.rotate(-16, resample=Image.BICUBIC, center=(big / 2, big / 2))
    icon = Image.alpha_composite(icon, tag_layer).convert("RGB")

    if not maskable:
        # Rounded corners for the PWA/favicon versions; launchers round the rest.
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, big - 1, big - 1], radius=int(big * 0.21), fill=255
        )
        flat = Image.new("RGB", (big, big), BRAND)
        icon = Image.composite(icon, flat, mask)

    return icon.resize((size, size), Image.LANCZOS)


def fit_font(text: str, path: str, max_size: int, max_width: int) -> ImageFont.FreeTypeFont:
    """Largest font size at or below max_size where the text fits in max_width."""
    size = max_size
    while size > 8:
        f = font(path, size)
        box = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=f)
        if box[2] - box[0] <= max_width:
            return f
        size -= 2
    return font(path, 8)


def make_og_image() -> Image.Image:
    """1200x630 link preview: the brand on the left, the actual maths on the right."""
    W, H = 1200, 630
    img = brand_background(H).resize((W, H), Image.BILINEAR)
    d = ImageDraw.Draw(img)

    # Left: the brand.
    d.text((72, 152), "Clear Price", font=font(BOLD, 92), fill=WHITE)
    d.text((76, 264), "What will I really pay?", font=font(REGULAR, 40), fill=PALE)
    d.text((76, 368), "20% off, then 70% off", font=font(BOLD, 38), fill=WHITE)
    d.text((76, 420), "= 76% off, not 90%.", font=font(REGULAR, 38), fill=PALE)

    # Right: the answer on a white card. Every row is measured and centred so
    # nothing can clip, whatever the currency or the number of digits.
    card = [660, 112, 1132, 518]
    d.rounded_rectangle(card, radius=36, fill=WHITE)
    inner_left, inner_right = card[0] + 46, card[2] - 46
    inner_w = inner_right - inner_left
    centre_x = (inner_left + inner_right) / 2

    def row(text: str, path: str, size: int, y: float, fill, *, fit: bool = True):
        f = fit_font(text, path, size, inner_w) if fit else font(path, size)
        box = d.textbbox((0, 0), text, font=f)
        x = centre_x - (box[2] - box[0]) / 2 - box[0]
        d.text((x, y - box[1]), text, font=f, fill=fill)
        return x, box, f

    # $89.00, struck through.
    f = font(REGULAR, 44)
    box = d.textbbox((0, 0), "$89.00", font=f)
    x = centre_x - (box[2] - box[0]) / 2
    d.text((x - box[0], 160 - box[1]), "$89.00", font=f, fill=(100, 116, 139))
    d.line(
        [(x - box[0], 160 - box[1] + (box[3] + box[1]) / 2), (x - box[0] + box[2], 160 - box[1] + (box[3] + box[1]) / 2)],
        fill=(100, 116, 139),
        width=4,
    )

    row("YOU PAY", BOLD, 30, 226, (71, 85, 105), fit=False)
    row("$21.36", BOLD, 108, 268, INK)
    row("You saved $67.64", BOLD, 40, 410, SAVED_GREEN)

    return img

    # Right: the answer, on a white card.
    card = [660, 118, 1130, 512]
    d.rounded_rectangle(card, radius=36, fill=WHITE)
    d.text((706, 168), "$89.00", font=font(REGULAR, 44), fill=(100, 116, 139))
    d.line([(710, 196), (838, 196)], fill=(100, 116, 139), width=4)
    d.text((706, 226), "YOU PAY", font=font(BOLD, 30), fill=(71, 85, 105))
    d.text((700, 274), "$21.36", font=font(BOLD, 108), fill=INK)
    d.text((706, 410), "You saved $67.64", font=font(BOLD, 40), fill=SAVED_GREEN)

    return img


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)

    make_icon(512).save(ICONS / "icon-512.png", optimize=True)
    make_icon(192).save(ICONS / "icon-192.png", optimize=True)
    make_icon(512, maskable=True).save(ICONS / "icon-maskable-512.png", optimize=True)
    # iOS ignores transparency and adds its own rounding.
    make_icon(180).save(ICONS / "apple-touch-icon.png", optimize=True)
    make_icon(32).save(ICONS / "favicon-32.png", optimize=True)
    make_og_image().save(PUBLIC / "og-image.png", optimize=True)

    for path in sorted(PUBLIC.rglob("*.png")):
        print(f"{path.relative_to(ROOT)}  ({path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
