"""Draw the social preview card (GitHub repository card and link previews).

    uv run --with pillow python docs/assets/make_social_card.py

Writes docs/assets/social-preview.png (1280x640, for GitHub: Settings > Social preview) and
web/public/og.png (1200x630, for the Open Graph tags of the web page).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
BG = (11, 13, 18)
PANEL = (22, 26, 36)
BORDER = (46, 52, 68)
TEXT = (240, 242, 247)
MUTED = (151, 160, 178)
INDIGO = (99, 102, 241)
VIOLET = (139, 92, 246)
SCALE = 2  # draw at twice the size, then shrink for smooth edges


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size * SCALE)


def gradient(size: tuple[int, int]) -> Image.Image:
    """Diagonal indigo-to-violet gradient, like the logo."""
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    assert px is not None
    for y in range(h):
        for x in range(w):
            t = (x / w + y / h) / 2
            px[x, y] = tuple(int(INDIGO[i] + (VIOLET[i] - INDIGO[i]) * t) for i in range(3))
    return img


def rounded(
    img: Image.Image, box: tuple[int, int, int, int], radius: int, fill: Image.Image
) -> None:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius, fill=255)
    img.paste(fill.resize(img.size), (0, 0), mask)


def logo(img: Image.Image, x: int, y: int, size: int) -> None:
    s = SCALE
    box = (x * s, y * s, (x + size) * s, (y + size) * s)
    rounded(img, box, int(size * 0.28) * s, gradient(img.size))
    d = ImageDraw.Draw(img)
    u = size * s / 32

    def pt(px: float, py: float) -> tuple[float, float]:
        return (x * s + px * u, y * s + py * u)

    for x1, x2, yy in ((10, 22, 11), (10, 18, 16), (10, 15, 21)):
        d.line([pt(x1, yy), pt(x2, yy)], fill="white", width=int(2 * u))
        for cx in (x1, x2):
            c = pt(cx, yy)
            d.ellipse([c[0] - u, c[1] - u, c[0] + u, c[1] + u], fill="white")
    c = pt(22.5, 21)
    d.ellipse([c[0] - 2.5 * u, c[1] - 2.5 * u, c[0] + 2.5 * u, c[1] + 2.5 * u], fill="white")


def pill(d: ImageDraw.ImageDraw, x: int, y: int, text: str) -> int:
    s = SCALE
    f = font(22)
    width = int(d.textlength(text, font=f)) // s + 40
    d.rounded_rectangle(
        [x * s, y * s, (x + width) * s, (y + 46) * s], 23 * s, fill=PANEL, outline=BORDER, width=s
    )
    d.text(((x + 20) * s, (y + 23) * s), text, font=f, fill=TEXT, anchor="lm")
    return width


def draw(w: int, h: int) -> Image.Image:
    s = SCALE
    img = Image.new("RGB", (w * s, h * s), BG)

    glow = Image.new("RGB", img.size, BG)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([int(w * 0.55) * s, -int(h * 0.35) * s, int(w * 1.15) * s, int(h * 0.65) * s],
               fill=(52, 50, 140))
    glow = glow.filter(ImageFilter.GaussianBlur(120 * s))
    img = Image.blend(img, glow, 0.9)
    d = ImageDraw.Draw(img)

    pad = 72
    cw, ch = int(w * 0.33), 330
    cx, cy = w - pad - cw, (h - ch) // 2  # the answer card, on the right
    oy = 56  # the left column is shifted down to sit in the middle

    logo(img, pad, 70 + oy, 72)
    d.text(((pad + 92) * s, 106 * s + oy * s), "VectorNote", font=font(46, True), fill=TEXT,
           anchor="lm")

    # The largest headline size whose longer line still ends before the card.
    room = (cx - pad - 40) * s
    size = 64
    while d.textlength("Get the page it came from.", font=font(size, True)) > room:
        size -= 1
    d.text((pad * s, (215 + oy) * s), "Ask your own notes.", font=font(size, True), fill=TEXT,
           anchor="ls")
    d.text((pad * s, (215 + oy + size + 10) * s), "Get the page it came from.",
           font=font(size, True), fill=(165, 168, 255), anchor="ls")
    sub_y = 215 + oy + size + 10 + 60
    d.text((pad * s, sub_y * s), "Offline, privacy-first RAG study assistant.",
           font=font(26), fill=MUTED, anchor="ls")

    x = pad
    for label in ("Runs offline", "Cited answers", "Hybrid search"):
        x += pill(d, x, sub_y + 34, label) + 14

    d.rounded_rectangle([cx * s, cy * s, (cx + cw) * s, (cy + ch) * s], 22 * s, fill=PANEL,
                        outline=BORDER, width=2 * s)
    d.rounded_rectangle([(cx + 24) * s, (cy + 24) * s, (cx + cw - 24) * s, (cy + 78) * s],
                        14 * s, fill=(34, 39, 54))
    d.text(((cx + 40) * s, (cy + 51) * s), "What is a mutex?", font=font(22), fill=TEXT,
           anchor="lm")
    lines = ("A mutex lets one thread at a time", "enter a critical section")
    for i, line in enumerate(lines):
        d.text(((cx + 28) * s, (cy + 124 + i * 34) * s), line, font=font(21), fill=TEXT,
               anchor="lm")
    line_width = int(d.textlength(lines[1], font=font(21))) // s
    chip = (cx + 28 + line_width + 10, cy + 124 + 34 - 14)
    d.rounded_rectangle([chip[0] * s, chip[1] * s, (chip[0] + 30) * s, (chip[1] + 28) * s],
                        9 * s, fill=INDIGO)
    d.text(((chip[0] + 15) * s, (chip[1] + 14) * s), "1", font=font(18, True), fill="white",
           anchor="mm")
    d.line([(cx + 28) * s, (cy + 214) * s, (cx + cw - 28) * s, (cy + 214) * s], fill=BORDER,
           width=s)
    d.text(((cx + 28) * s, (cy + 252) * s), "[1] os-lecture.pdf, p. 2", font=font(20),
           fill=MUTED, anchor="lm")
    d.text(((cx + 28) * s, (cy + 288) * s), "100% hit@3 on 35 questions", font=font(20),
           fill=(110, 231, 183), anchor="lm")

    return img.resize((w, h), Image.Resampling.LANCZOS)


def main() -> None:
    draw(1280, 640).save(ROOT / "docs/assets/social-preview.png", optimize=True)
    draw(1200, 630).save(ROOT / "web/public/og.png", optimize=True)


if __name__ == "__main__":
    main()
