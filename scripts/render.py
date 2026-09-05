#!/usr/bin/env python3
"""
render.py — transforme le corpus en écrans 800x480 prêts pour l'e-ink.

Pour chaque brevet : télécharge les planches, les note, garde la meilleure
(ou compose un montage), et écrit un PNG 1 bit.
"""
import io
import json
import os
import random
import sys
import urllib.request

from PIL import Image, ImageOps, ImageDraw, ImageFont

# Cibles matérielles. Le trait fin d'un dessin de brevet survit beaucoup mieux
# à un niveau de gris antialiasé qu'à un tramage 1 bit : on quantifie au nombre
# de niveaux réellement supportés par l'appareil plutôt que de trancher en noir/blanc.
TARGETS = {
    "og": {"w": 800, "h": 480, "levels": 4, "scale": 1.0},
    "x": {"w": 1872, "h": 1404, "levels": 16, "scale": 2.3},
}
W, H = 800, 480
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
UA = {"User-Agent": "Mozilla/5.0 (compatible; TrmnlPatentPlugin/1.0)"}


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return Image.open(io.BytesIO(r.read()))


def trim(im):
    """Recadre les marges blanches."""
    im = im.convert("L")
    bb = ImageOps.invert(im).getbbox()
    return im.crop(bb) if bb else im


def strip_header(im):
    """
    Retire le bandeau officiel imprimé en haut des planches
    ("U.S. Patent — Sheet 3 of 5 — Des. 421,005"), qui parasite le rendu.
    On cherche une bande fine isolée par du blanc dans le quart supérieur.
    """
    w, h = im.size
    px = im.point(lambda v: 255 if v < 200 else 0)
    rows = [sum(px.crop((0, y, w, y + 1)).getdata()) // 255 for y in range(min(h, int(h * 0.28)))]
    if not rows:
        return im
    band_end = None
    seen_ink = False
    blank = 0
    for y, v in enumerate(rows):
        if v > w * 0.01:
            seen_ink = True
            blank = 0
        elif seen_ink:
            blank += 1
            if blank > h * 0.02:      # vide franc après une bande de texte
                band_end = y
                break
    if band_end and band_end < h * 0.14:
        return im.crop((0, band_end, w, h))
    return im


def score(im):
    """
    Note une planche. On cherche une figure lisible une fois réduite :
    ni trop étirée, ni trop vide, ni trop dense (planche multi-figures surchargée).
    Renvoie None si la planche est à écarter.
    """
    w, h = im.size
    if w < 200 or h < 200:
        return None
    ratio = w / h
    if ratio > 3.5 or ratio < 0.28:
        return None

    # densité d'encre mesurée en pleine résolution : réduire d'abord efface
    # les traits fins et fait passer de bonnes planches pour des pages blanches
    hist = im.point(lambda v: 255 if v < 200 else 0).histogram()
    ink = hist[255] / float(w * h)
    if ink < 0.022 or ink > 0.30:
        return None

    s = 0.0
    # une vue en perspective a de la matière ; une vue de profil est presque vide
    s += 3.0 - abs(0.11 - ink) * 14
    # les ratios proches du carré ou légèrement portrait passent le mieux
    s += 1.5 - abs(0.85 - ratio)
    return s


def best_figures(urls, want=1, cap=6):
    """Télécharge jusqu'à `cap` planches et renvoie les `want` meilleures.

    Bonus aux premières planches : sur un brevet de dessin, FIG. 1 est
    presque toujours la vue en perspective, la plus lisible de loin.
    """
    scored = []
    for i, u in enumerate(urls[:cap]):
        try:
            im = trim(strip_header(trim(fetch(u))))
        except Exception:
            continue
        sc = score(im)
        if sc is not None:
            scored.append((sc + max(0, 1.2 - i * 0.35), im))
    scored.sort(key=lambda t: -t[0])
    return [im for _, im in scored[:want]]


def fit(im, bw, bh):
    r = min(bw / im.width, bh / im.height)
    return im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)


def quantize(im, levels):
    """Réduit au nombre de niveaux de gris de l'appareil, sans tramage."""
    step = 255.0 / (levels - 1)
    return im.point(lambda v: int(round(v / step) * step))


def compose(patent, figs, out, target="og"):
    t = TARGETS[target]
    W, H, k = t["w"], t["h"], t["scale"]
    c = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(c)
    bold = ImageFont.truetype(FB, int(30 * k))
    reg = ImageFont.truetype(FR, int(22 * k))
    small = ImageFont.truetype(FR, int(18 * k))

    art_x, art_w = int(340 * k), int(430 * k)
    art_h = H - int(80 * k)   # le X est en 4:3 : on remplit la hauteur disponible
    if len(figs) == 1:
        a = fit(figs[0], art_w, art_h)
        c.paste(a, (art_x + (art_w - a.width) // 2, (H - a.height) // 2))
    else:
        cols = 2 if len(figs) > 2 else len(figs)
        rows = (len(figs) + cols - 1) // cols
        cw, ch = art_w // cols, art_h // rows
        for i, f in enumerate(figs):
            a = fit(f, cw - int(14 * k), ch - int(14 * k))
            cx = art_x + (i % cols) * cw + (cw - a.width) // 2
            cy = int(40 * k) + (i // cols) * ch + (ch - a.height) // 2
            c.paste(a, (cx, cy))

    x0 = int(40 * k)
    d.text((x0, int(62 * k)), patent["title"][:34], font=bold, fill=0)
    d.line([(x0, int(106 * k)), (int(300 * k), int(106 * k))], fill=0, width=max(2, int(2 * k)))
    if patent.get("assignee"):
        d.text((x0, int(126 * k)), patent["assignee"][:28], font=reg, fill=80)
    if patent.get("year"):
        d.text((x0, int(158 * k)), str(patent["year"]), font=reg, fill=80)
    d.text((x0, H - int(62 * k)), patent["number"], font=small, fill=80)
    d.text((x0, H - int(38 * k)), "U.S. Patent Office", font=small, fill=120)

    q = quantize(c, t["levels"])
    # palette indexée : même rendu, fichier plus léger que du L 8 bits
    q.convert("P", palette=Image.ADAPTIVE, colors=t["levels"]).save(out, optimize=True)
    return out


if __name__ == "__main__":
    corpus = json.load(open(sys.argv[1]))
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    mode = sys.argv[3] if len(sys.argv) > 3 else "auto"
    os.makedirs("/mnt/user-data/outputs/apercus", exist_ok=True)

    random.seed(7)
    picks = random.sample(corpus, min(n * 3, len(corpus)))
    made = 0
    for p in picks:
        if made >= n:
            break
        want = 1 if mode == "single" else (3 if mode == "montage" else 1)
        figs = best_figures(p["figures"], want=want)
        if not figs:
            print(f"  écarté  {p['number']} ({p['title'][:30]}) — aucune planche exploitable")
            continue
        target = os.environ.get("TARGET", "og")
        out = f"/mnt/user-data/outputs/apercus/{p['number']}_{mode}_{target}.png"
        compose(p, figs, out, target)
        print(f"  ok      {p['number']} · {len(figs)} planche(s) · {p['title'][:34]}")
        made += 1
