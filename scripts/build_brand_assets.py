"""Generate the wanchurk-studio brand assets from the approved logo A geometry.

Geometry is defined on a 512-unit grid and scaled per output size, so the
mark stays identical from the 300px preview down to 16px favicons.
"""

from pathlib import Path

from PIL import Image, ImageDraw

BG = (0x8B, 0x3A, 0x1C)
FG = (0xF5, 0xED, 0xE4)
DOT = (0xF2, 0xB9, 0x4B)

ROOT = Path("/Users/wanchurk/wanchurk-studio")
SS = 8  # supersample factor for smooth edges


def render(size: int, transparent_corners: bool = True) -> Image.Image:
    big = size * SS
    s = big / 512.0
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=int(112 * s), fill=BG + (255,))
    pts = [(118, 176), (186, 336), (256, 196), (326, 336), (394, 176)]
    pts = [(x * s, y * s) for x, y in pts]
    w = int(44 * s)
    d.line(pts, fill=FG + (255,), width=w, joint="curve")
    r = int(34 * s)
    cx, cy = 394 * s, 112 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=DOT + (255,))
    # round line caps
    for x, y in (pts[0], pts[-1]):
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=FG + (255,))
    return img.resize((size, size), Image.LANCZOS)


def save_png(size: int, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    render(size).save(path, "PNG", optimize=True)


def main() -> None:
    fav = ROOT / "static" / "favicon"
    img = ROOT / "static" / "img"
    save_png(1024, ROOT / "static" / "brand" / "wanchurk-studio-mark-1024.png")
    save_png(16, fav / "favicon-16x16.png")
    save_png(32, fav / "favicon-32x32.png")
    save_png(96, fav / "favicon-96x96.png")
    save_png(180, fav / "apple-touch-icon.png")
    save_png(192, fav / "web-app-manifest-192x192.png")
    save_png(512, fav / "web-app-manifest-512x512.png")
    # ICO with multiple embedded sizes
    base = render(256)
    base.save(fav / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])
    # Image used by auth pages (was wanchurk-studio-logo.webp)
    render(256).save(img / "wanchurk-studio-logo.png", "PNG", optimize=True)
    # Dark-mode-neutral SVG favicon, same geometry
    (fav / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        '<rect width="512" height="512" rx="112" fill="#8B3A1C"/>'
        '<path d="M118 176 L186 336 L256 196 L326 336 L394 176" fill="none" stroke="#F5EDE4" '
        'stroke-width="44" stroke-linecap="round" stroke-linejoin="round"/>'
        '<circle cx="394" cy="112" r="34" fill="#F2B94B"/></svg>\n',
        encoding="utf-8",
    )
    print("generated")


if __name__ == "__main__":
    main()
