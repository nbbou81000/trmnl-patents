# TRMNL — Patent Drawings

Affiche au hasard un appareil technologique — console, téléphone, liseuse, ordinateur —
sous forme de dessin technique de brevet américain. Rotation toutes les 5 minutes.

```
terms.json → collect.js → corpus.json → build.py → docs/img/*.png → GitHub Pages → plugin
```

## Pourquoi cette architecture

Le plugin ne dépend d'aucune API en production. Une fois le corpus d'images généré,
l'appareil ne fait qu'afficher une URL statique. Aucun flux ne peut tomber,
aucun quota ne peut être dépassé, aucun catalogue n'est à maintenir.

## 1. Collecte (`scripts/collect.js`)

Source : l'endpoint de recherche JSON de Google Patents, qui renvoie pour 100 brevets
d'un coup le titre, le déposant, les dates **et l'URL pleine résolution de chaque planche**.
On ne touche jamais aux pages HTML : ce sont elles qui déclenchent le blocage anti-robot.

L'astuce de ciblage : tous les brevets de dessin américains contiennent la formule
`the ornamental design for a[n] <objet>`. La recherche sur cette phrase exacte isole
les design patents avec une précision proche de 100 %.

⚠️ L'article compte. `for an electronic reader`, jamais `for a`. Les termes commençant
par une voyelle renvoient zéro sans cette correction.

**Cadence.** Le moteur bloque autour de 20-25 requêtes par IP, avec un refroidissement
de plus de dix minutes. D'où le workflow horaire : chaque exécution GitHub Actions part
d'une IP différente. `state.json` mémorise la position par terme, la collecte reprend seule.
85 termes × jusqu'à 10 pages = 2 à 3 jours de fond de tâche.

## 2. Rendu (`scripts/render.py`, `scripts/build.py`)

Sélection de planche, par ordre d'importance :

- rejet des ratios extrêmes et des densités d'encre aberrantes ;
- bonus aux premières figures — sur un design patent, FIG. 1 est presque toujours
  la vue en perspective, la plus lisible de loin ;
- retrait du bandeau officiel (`U.S. Patent — Sheet 3 of 5 — Des. 421,005`)
  par analyse du profil d'encre horizontal ;
- exclusion des accessoires (housses, supports, coques) et des brevets d'interface
  graphique : 19 % du corpus, et autant d'affichages sans intérêt.

**Niveaux de gris, pas de tramage.** Le trait fin d'un dessin de brevet est détruit par
un dither Floyd-Steinberg. On redimensionne en niveaux de gris avec LANCZOS puis on
quantifie : 4 niveaux pour l'OG, 16 pour le X. Les hachures de volume survivent.

**Une seule résolution stockée** : 1872×1404, celle du TRMNL X. La mise en page étant
proportionnelle, l'OG reçoit la même image réduite par le moteur de rendu.
Palette 16 couleurs, ~56 ko par image, ~110 Mo pour 2000 images.

## 3. Rotation (`full.liquid`)

Aucun serveur, aucun polling de données. L'index dérive de l'horodatage que TRMNL
injecte dans chaque plugin :

```liquid
{% assign slot = trmnl.system.timestamp_utc | divided_by: 300 | floor %}
{% assign idx = slot | modulo: count %}
```

Le `floor` est nécessaire : sans lui, `divided_by` renvoie un flottant et l'index sort à 0.07.

Le corpus est mélangé avec une graine fixe au moment du rendu, donc l'incrément
séquentiel donne un contenu aléatoire. Avec 2000 images, il faut 7 jours pour boucler.
La séquence est identique pour tous les appareils : deux personnes voient le même
appareil au même moment.

Le plugin ne lit que `docs/count.json` (quelques octets). Titre, déposant et année
sont gravés dans l'image, il n'y a rien d'autre à transmettre.

## Limites connues

- **Pas de nom de modèle.** Les titres de design patents sont génériques par obligation
  légale : le brevet du premier iPhone s'intitule « Electronic device ». Aucun lien
  produit↔brevet exploitable côté Wikidata. Le déposant et l'année sont disponibles à 100 %.
  Pour les appareils iconiques, un fichier d'annotation manuel reste la seule voie fiable.
- Le rendement des termes à voyelle n'a pas été mesuré : le blocage du moteur est survenu
  pendant les tests. À vérifier à la première exécution réelle.

## Droits

Les brevets américains sont des publications officielles du gouvernement, sans protection
par copyright. Les images sont servies par le bucket public de Google Patents.
