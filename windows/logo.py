"""Vox logo drawn with Pillow: a white V with a recording dot on a gradient rounded square.

Used for the tray icon (colour changes with state) and to generate vox.ico:
    python logo.py        writes vox.ico next to this file
"""
from PIL import Image, ImageDraw

THEMES = {
    "idle": ("#3D6BFF", "#7A4DFF"),
    "rec": ("#FF5A5F", "#D7263D"),
    "busy": ("#F7B32B", "#F07B1E"),
}


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def draw(size=64, state="idle", dot=True):
    s = size * 4  # supersample, then shrink for smooth edges
    a, b = (_rgb(c) for c in THEMES.get(state, THEMES["idle"]))
    grad = Image.new("RGBA", (s, s))
    px = grad.load()
    for y in range(s):
        for x in range(s):
            t = (x + y) / (2 * (s - 1))
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.227), fill=255)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    k = s / 512
    # small sizes get a thicker V so it stays readable in the tray
    w = int((58 if size >= 48 else 70) * k)
    pts = [(140 * k, 150 * k), (256 * k, 380 * k), (372 * k, 150 * k)]
    d.line(pts, fill="white", width=w, joint="curve")
    for x, y in (pts[0], pts[2]):
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill="white")
    if dot and state == "idle":
        cx, cy, r, ring = 386 * k, 128 * k, 34 * k, 10 * k
        d.ellipse((cx - r - ring, cy - r - ring, cx + r + ring, cy + r + ring), fill="white")
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="#FF5A5F")
    return img.resize((size, size), Image.LANCZOS)


def write_ico(path):
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    imgs = [draw(n) for n in sizes]
    imgs[-1].save(path, format="ICO", sizes=[(n, n) for n in sizes], append_images=imgs[:-1])


if __name__ == "__main__":
    import os
    write_ico(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vox.ico"))
