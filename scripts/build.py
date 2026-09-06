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
import subprocess
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
CHECKPOINT = int(os.environ.get("CHECKPOINT", "100"))   # commit intermédiaire
TIME_BUDGET = int(os.environ.get("TIME_BUDGET", "9000"))   # 2 h 30


def save_manifest(items):
    json.dump(
        {"count": len(items), "generated_at": int(time.time()), "items": items},
        open(MANIFEST, "w"),
        indent=1,
    )
    json.dump({"count": len(items)}, open("docs/count.json", "w"))


def checkpoint(items):
    """
    Commit intermédiaire : un job annulé ou planté perd tout ce qui n'a pas
    été poussé, et le disque du runner est jeté avec lui.
    Échec silencieux : hors CI (test local), il n'y a pas de dépôt git.
    """
    save_manifest(items)
    try:
        subprocess.run(["git", "add", "docs"], check=True, capture_output=True)
        r = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if r.returncode == 0:
            return
        subprocess.run(["git", "commit", "-m", f"images: {len(items)} écrans (checkpoint)"],
                       check=True, capture_output=True)
        # Le workflow de collecte commite corpus.json pendant que le rendu tourne.
        # Sans rebase, la poussée est rejetée ("fetch first") et la passe échoue.
        for attempt in range(3):
            try:
                subprocess.run(["git", "push"], check=True, capture_output=True)
                print(f"  ✓ checkpoint poussé à {len(items)} images")
                return
            except subprocess.CalledProcessError:
                subprocess.run(["git", "pull", "--rebase", "--autostash"],
                               check=True, capture_output=True)
        print("  (checkpoint non poussé après 3 tentatives)")
    except Exception as e:
        print(f"  (checkpoint ignoré : {e})")


def main(corpus_path, cap):
    corpus = json.load(open(corpus_path))
    os.makedirs(OUT_IMG, exist_ok=True)

    done = {}
    if os.path.exists(MANIFEST):
        done = {e["number"]: e for e in json.load(open(MANIFEST))["items"]}

    # Sélection stratifiée par catégorie.
    #
    # Un simple mélange conserverait les proportions du corpus, et celles-ci sont
    # très déséquilibrées : les termes larges ("telephone", "mobile phone")
    # saturent leur plafond de 1000 quand un terme précis n'apporte qu'une poignée
    # de brevets. À plat, les trois quarts des planches seraient des téléphones.
    #
    # On mélange donc chaque catégorie séparément, puis on pioche en tourniquet :
    # chaque terme fournit une planche à tour de rôle, et les catégories rares
    # sont épuisées avant que les grosses aient rendu tout leur stock.
    random.seed(1789)
    buckets = {}
    for item in sorted(corpus, key=lambda p: p["number"]):
        buckets.setdefault(item.get("term", "divers"), []).append(item)
    for b in buckets.values():
        random.shuffle(b)

    order = sorted(buckets, key=lambda k: len(buckets[k]))
    pool = []
    while any(buckets[k] for k in order):
        for k in order:
            if buckets[k]:
                pool.append(buckets[k].pop())

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
        idx = len(items)
        rel = f"img/{idx}.png"
        try:
            figs = best_figures(p["figures"], want=want, cap=5)
            if not figs:
                skipped += 1
                continue
            # une planche corrompue ne doit pas faire tomber toute la passe
            compose(p, figs, os.path.join("docs", rel), target="x")
        except Exception as e:
            print(f"  {p['number']} ignoré : {type(e).__name__}")
            skipped += 1
            continue
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
        if made % CHECKPOINT == 0:
            checkpoint(items)
        time.sleep(DELAY)

    # Le manifeste allégé (docs/count.json) est le seul lu par le plugin :
    # quelques dizaines d'octets. Titre, déposant et année sont gravés dans l'image.
    save_manifest(items)
    total = sum(os.path.getsize(os.path.join("docs", i["file"])) for i in items)
    print(f"\n{len(items)} images · {skipped} brevets écartés · {total / 1048576:.1f} Mo")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2000)
