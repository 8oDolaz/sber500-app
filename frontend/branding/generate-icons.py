"""Rasterize the Figma 71:5960 composition; requires Pillow (no build-time dependency)."""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parent / "apps/pwa/public"
SIZE = 1024
source = Image.open(HERE / "mascot-source.png").convert("RGBA")
# Exact Figma image slot: 1197 × 1197, x=-87, y=166 inside the 1024 square.
square = Image.new("RGBA", (SIZE, SIZE), "black")
square.alpha_composite(source.resize((1197, 1197), Image.Resampling.LANCZOS), (-87, 166))

# Rounded avatar and its subtle inset rim. Supersampling keeps the edge smooth at icon sizes.
scale = 4
mask = Image.new("L", (SIZE * scale, SIZE * scale), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIZE * scale - 1, SIZE * scale - 1), radius=260 * scale, fill=255)
rim = Image.new("RGBA", mask.size)
ImageDraw.Draw(rim).rounded_rectangle((6, 6, SIZE * scale - 6, SIZE * scale - 6), radius=258.5 * scale, outline=(181, 211, 231, 191), width=3 * scale)
avatar = Image.alpha_composite(square, rim.resize((SIZE, SIZE), Image.Resampling.LANCZOS))
avatar.putalpha(mask.resize((SIZE, SIZE), Image.Resampling.LANCZOS))
avatar.save(HERE / "icon-source.png", optimize=True)

for size in (64, 192, 512):
    avatar.resize((size, size), Image.Resampling.LANCZOS).save(PUBLIC / f"pwa-{size}x{size}.png", optimize=True)
avatar.resize((32, 32), Image.Resampling.LANCZOS).save(PUBLIC / "favicon-32x32.png", optimize=True)
avatar.save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
# iOS and Android provide their own platform masks. Both outputs are opaque.
apple = Image.new("RGB", (SIZE, SIZE), "black")
apple.paste(avatar, mask=avatar.getchannel("A"))
apple.resize((180, 180), Image.Resampling.LANCZOS).save(PUBLIC / "apple-touch-icon-180x180.png", optimize=True)
# Keep the same mascot crop, with a full-bleed background for any launcher mask.
square.convert("RGB").resize((512, 512), Image.Resampling.LANCZOS).save(PUBLIC / "maskable-icon-512x512.png", optimize=True)
