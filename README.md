# Patent Drawings — TRMNL plugin

**A random U.S. design patent drawing on your TRMNL e-ink display: consoles, phones, cameras, e-readers and other devices, exactly as their designers first filed them.**

[![Install on TRMNL](https://img.shields.io/badge/TRMNL-Install%20recipe-black?style=flat-square)](https://trmnl.com/recipes/469103)
![Drawings](https://img.shields.io/badge/drawings-10%2C857-orange?style=flat-square)
![Server cost](https://img.shields.io/badge/server%20cost-0%20%E2%82%AC-brightgreen?style=flat-square)
![Public domain](https://img.shields.io/badge/images-public%20domain-blue?style=flat-square)

![Patent Drawings on a TRMNL display](https://trmnl-public.s3.us-east-2.amazonaws.com/78qvifiqxfnxdryhoq64goxk5aln)

---

## What it does

Every 5 minutes the screen shows a new design patent drawing, picked from a corpus of **10,857 ready-to-display plates**. Each plate carries the patent title, the assignee (the company or person who filed it) and the year.

Patent drawings are pure line art with fine hatching for volume: they look like they were made for e-ink.

## Installation

1. Open the recipe page: **[trmnl.com/recipes/469103](https://trmnl.com/recipes/469103)**
2. Click **Install** and add it to a playlist.

No settings, no API key, no account.

## Browse the gallery

Every drawing in the corpus can also be browsed on the web:
**[nbbou81000.github.io/trmnl-patents](https://nbbou81000.github.io/trmnl-patents/)**

---

## How it works

All images are **rendered once in advance and served as static files from GitHub Pages**. The device never calls a patent search engine: if Google Patents went down tomorrow, the plugin would keep working.

```
terms.json ──► collect.js ──► corpus.json ──► build.py ──► docs/img/N.png + docs/plate/N.json
                (Google Patents)   (28,124 patents)   (select, clean, quantize)        │
                                                                                      ▼
                                                     GitHub Pages ──► TRMNL ──► e-ink screen
```

### 1. Collecting patents — `scripts/collect.js`

Every U.S. design patent contains the legal phrase *"the ornamental design for a[n] &lt;object&gt;"*. Searching Google Patents' JSON endpoint for that exact phrase isolates design patents almost perfectly, and returns the full-resolution URL of every drawing sheet in one call — no HTML scraping.

- **176 search terms** in `terms.json` (mobile phone, camera, game console, printer, vending machine, parking meter…).
- The article matters: `for an electronic reader`, never `for a` — vowel terms return nothing otherwise.
- The search engine blocks an IP after ~20–25 requests. `state.json` remembers where each term stopped, so collection resumes on the next run.

### 2. Rendering plates — `scripts/render.py`, `scripts/build.py`

For each patent, the best drawing sheet is chosen and turned into an e-ink screen:

- sheets with extreme ratios or abnormal ink density are rejected;
- early figures get a bonus — on a design patent, FIG. 1 is almost always the perspective view, the most readable from a distance;
- the official header (`U.S. Patent — Sheet 3 of 5 — Des. 421,005`) is cropped out by analysing the horizontal ink profile;
- accessories (cases, stands, chargers…) and graphical-user-interface patents are excluded.

**Grayscale, not dithering.** Floyd–Steinberg dithering destroys the thin lines of a patent drawing. Images are downscaled in grayscale (LANCZOS) then quantized, so the hatching survives.

**One resolution stored**: 1872×1404 (TRMNL X). The layout is proportional, so TRMNL OG receives the same image scaled down by the renderer.

### 3. Rotation — no server, no random draw

The index is derived from the timestamp TRMNL injects into every plugin:

```liquid
{% assign slot = trmnl.system.timestamp_utc | divided_by: 300 | floor %}
{% assign idx = slot | modulo: count %}
```

`floor` is required: without it `divided_by` returns a float and the index is wrong. The corpus is shuffled with a fixed seed at build time, so a sequential index looks random — and every device shows the same drawing at the same moment.

### Data endpoints

| URL | Content |
|---|---|
| `https://nbbou81000.github.io/trmnl-patents/img/N.png` | The rendered plate |
| `https://nbbou81000.github.io/trmnl-patents/plate/N.json` | Title, assignee, year and corpus size |
| `https://nbbou81000.github.io/trmnl-patents/count.json` | Number of plates (`{"count": 10857}`) |

```json
{"i": 0, "image": "img/0.png", "title": "Mobile phone", "assignee": "Samsung Electronics Co., Ltd.", "year": 2013, "count": 10857}
```

---

## Repository layout

| Path | Role |
|---|---|
| `terms.json` | The 176 device names searched on Google Patents |
| `scripts/collect.js` | Collects patents and drawing URLs into `corpus.json` (resumable via `state.json`) |
| `scripts/render.py` | Picks the best sheet, crops the header, quantizes to grayscale |
| `scripts/build.py` | Builds `docs/img/`, `docs/plate/`, `docs/count.json` and `docs/manifest.json`; commits every 100 images |
| `scripts/add_count.py` | One-off migration adding the `count` field to older plate files |
| `full.liquid` | Template reference for the TRMNL **Full** layout |
| `docs/` | Everything served by GitHub Pages, including the gallery `index.html` |

### Workflows

| Workflow | Trigger | Does |
|---|---|---|
| Collect patents | Manual (optional `only` input to target some terms) | `collect.js` |
| Render images | Twice a day + manual (`cap`, `only` inputs) | `build.py`, up to 500 new images per run |
| Add count field | Manual | `add_count.py` |

No secret is needed.

## In numbers

- **28,124** design patents collected, **10,857** rendered plates
- **176** device categories — printers, phones, remote controls, TVs, earphones, cameras, projectors…
- ~70 KB per plate, ~750 MB of images in total

## Known limitations

- **No model names.** Design patent titles are generic by law: the first iPhone's patent is simply titled *"Electronic device"*. The assignee and the year are always available, the product name is not.

## Credits

- Drawings from U.S. design patents, official U.S. government publications that are not protected by copyright. Patent data and images retrieved through [Google Patents](https://patents.google.com/).
- Built for [TRMNL](https://trmnl.com).

## Author

Made by **Nicolas Bouteiller** — [@nbbou81000](https://github.com/nbbou81000) · nb.bouteiller@gmail.com

If you enjoy it, you can [buy me a coffee on Ko-fi](https://ko-fi.com/nicolasbouteiller) ☕

## License

Code under the MIT License — see [`LICENSE`](LICENSE).
