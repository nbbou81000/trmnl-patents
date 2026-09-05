#!/usr/bin/env python3
"""
build.py — produit le corpus d'images final.

Parcourt corpus.json, télécharge les planches, garde les meilleures,
compose un écran et écrit docs/img/NNNN.png + docs/manifest.json.

Une seule résolution stockée (1872x1404, celle du TRMNL X) : la mise en page
étant proportionnelle, l'OG reçoit la même image réduite par le moteur de rendu.
Stocker deux formats doublerait le poids du dépôt sans gain visible.

  python3 scripts/build.py corpus.json 2000
"""
import json
import os
import random
import re
import sys
import time

# Les recherches ramènent aussi des accessoires : housses, supports, chargeurs.
# Ce ne sont pas des appareils, et leurs planches ne montrent rien d'intéressant.
EXCLUDE = re.compile(
    r"\b(case|cover|holder|stand|mount|bracket|adapter|adaptor|protector|"
    r"sleeve|pouch|strap|band|cable|charger|dock|skin|shell|grip|tray|"
    r"housing|bezel|frame for|combined with|packaging|carton|"
    r"icon|graphical user interface|display screen with)\b",
    re.I,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import best_figures, compose  # noqa: E402

OUT_IMG = "docs/img"
MANIFEST = "docs/manifest.json"
DELAY = 0.4          # pacing sur le CDN d'images
MAX_FIGS = 3

# Un job GitHub Actions est tué à 6 h et tout le travail non commité est perdu.
# On borne chaque passe en nombre d'images ET en durée : le reste est repris
# à l'exécution suivante grâce au manifeste.
PER_RUN = int(os.environ.get("PER_RUN", "500"))
TIME_BUDGET = int(os.environ.get("TIME_BUDGET", "9000"))   # 2 h 30


def main(corpus_path, cap):
    corpus = json.load(open(corpus_path))
    os.makedirs(OUT_IMG, exist_ok=True)

    done = {}
    if os.path.exists(MANIFEST):
        done = {e["number"]: e for e in json.load(open(MANIFEST))["items"]}

    # ordre stable et mélangé : la rotation par horodatage paraît aléatoire
    # sans qu'aucun tirage n'ait lieu côté appareil
    random.seed(1789)
    pool = sorted(corpus, key=lambda p: p["number"])
    random.shuffle(pool)

    items = list(done.values())
    skipped = 0
    made = 0
    started = time.time()

    for p in pool:
        if len(items) >= cap:
            break
        if made >= PER_RUN:
            print(f"  plafond de {PER_RUN} images atteint pour cette passe")
            break
        if time.time() - started > TIME_BUDGET:
            print("  budget temps atteint, reprise à la prochaine exécution")
            break
        if p["number"] in done:
            continue
        if EXCLUDE.search(p["title"] or ""):
            skipped += 1
            continue

        want = random.choice([1, 1, 2, 3])   # alterne vue seule et montage
        try:
            figs = best_figures(p["figures"], want=want, cap=5)
        except Exception:
            figs = []
        if not figs:
            skipped += 1
            continue

        idx = len(items)
        rel = f"img/{idx}.png"
        compose(p, figs, os.path.join("docs", rel), target="x")
        items.append({
            "i": idx,
            "number": p["number"],
            "title": p["title"],
            "assignee": p["assignee"],
            "year": p["year"],
            "figures": len(figs),
            "file": rel,
        })
        made += 1
        if len(items) % 25 == 0:
            print(f"  {len(items)} images · {skipped} écartés")
        time.sleep(DELAY)

    json.dump(
        {"count": len(items), "generated_at": int(time.time()), "items": items},
        open(MANIFEST, "w"),
        indent=1,
    )
    # Le plugin ne lit que celui-ci : quelques dizaines d'octets au lieu de 300 ko.
    # Titre, déposant et année sont déjà gravés dans l'image, rien d'autre à transmettre.
    json.dump({"count": len(items)}, open("docs/count.json", "w"))
    total = sum(os.path.getsize(os.path.join("docs", i["file"])) for i in items)
    print(f"\n{len(items)} images · {skipped} brevets écartés · {total / 1048576:.1f} Mo")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2000)
