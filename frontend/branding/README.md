# kainem application icon

Source: [Figma node 71:5960](https://www.figma.com/design/IwoVYL8aolHhH1kRNyTvLg/Untitled?node-id=71-5960).

`mascot-source.png` is the unchanged image asset supplied by Figma. `icon-source.png` reproduces the 1024 × 1024 composition: black background, the 1197 × 1197 image at (-87, 166), radius 260, and the 3px soft rim. The in-screen vector mascot is a separate artwork from the home design.

The generated files in `apps/pwa/public/` are committed and need no image tooling to build or deploy:

| File | Purpose |
| --- | --- |
| `favicon-32x32.png`, `favicon.ico` (16/32/48) | Website tabs and bookmarks |
| `apple-touch-icon-180x180.png` | iOS home screen, opaque background |
| `pwa-192x192.png`, `pwa-512x512.png` | Standard PWA icons |
| `maskable-icon-512x512.png` | Android launcher, opaque full-bleed black background |
| `pwa-64x64.png` | Small app/avatar asset |

The maskable version keeps the same crop without a baked outer corner mask or rim; the eyes remain inside the central safe circle. The browser/OS applies the launcher mask. Regenerate only when the Figma source changes:

```bash
python3 -m pip install Pillow  # optional authoring dependency
python3 frontend/branding/generate-icons.py
```
