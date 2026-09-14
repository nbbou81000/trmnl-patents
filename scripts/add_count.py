#!/usr/bin/env python3
"""
add_count.py — migration ponctuelle.

Les fichiers docs/plate/*.json écrits avant ce correctif n'ont pas le champ
"count". build.py ne les régénère jamais (il saute ce qui existe déjà), donc
un simple relancement du rendu ne les corrige pas. Ce script les complète
directement, sans retoucher les images ni retélécharger quoi que ce soit
depuis Google — juste une lecture/écriture de petits fichiers JSON.

  python3 scripts/add_count.py
"""
import json
import os
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLATE_DIR = os.path.join(ROOT, "docs", "plate")
COUNT_FILE = os.path.join(ROOT, "docs", "count.json")
CHECKPOINT = int(os.environ.get("CHECKPOINT", "1000"))


def commit(n):
    try:
        subprocess.run(["git", "add", "docs/plate"], check=True, capture_output=True)
        if subprocess.run(["git", "diff", "--staged", "--quiet"]).returncode == 0:
            return
        subprocess.run(["git", "commit", "-m", f"migrate: count field on {n} plates"],
                       check=True, capture_output=True)
        for _ in range(3):
            try:
                subprocess.run(["git", "push"], check=True, capture_output=True)
                print(f"  ✓ {n} fichiers poussés")
                return
            except subprocess.CalledProcessError:
                subprocess.run(["git", "pull", "--rebase", "--autostash"],
                               check=True, capture_output=True)
    except Exception as e:
        print(f"  (commit ignoré : {e})")


def main():
    total = json.load(open(COUNT_FILE))["count"]
    files = sorted(f for f in os.listdir(PLATE_DIR) if f.endswith(".json"))
    started = time.time()
    done = skipped = 0

    for f in files:
        path = os.path.join(PLATE_DIR, f)
        d = json.load(open(path))
        if "count" in d:
            skipped += 1
            continue
        d["count"] = total
        json.dump(d, open(path, "w"), ensure_ascii=False)
        done += 1
        if done % CHECKPOINT == 0:
            print(f"  {done} migrés · {skipped} déjà à jour")
            commit(done)
        if time.time() - started > 9000:
            print("  budget temps atteint, reprise à la prochaine exécution")
            break

    commit(done)
    print(f"\n{done} fichiers migrés · {skipped} déjà à jour · total {total}")


if __name__ == "__main__":
    main()
