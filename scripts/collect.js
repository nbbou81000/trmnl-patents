#!/usr/bin/env node
/**
 * collect.js — constitue le corpus de brevets de dessin (design patents) US.
 *
 * Source : l'endpoint de recherche JSON de Google Patents. Une requête = 100 brevets
 * avec titre, déposant, dates ET l'URL pleine résolution de chaque planche.
 * On ne touche jamais aux pages HTML : c'est elles qui déclenchent le blocage anti-robot.
 *
 * Reprend là où il s'est arrêté (state.json) pour étaler la collecte sur plusieurs jours.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const TERMS_FILE = path.join(ROOT, "terms.json");
const ASSIGNEES_FILE = path.join(ROOT, "assignees.json");
const CORPUS = path.join(ROOT, "corpus.json");
const STATE = path.join(ROOT, "state.json");

const UA = { "User-Agent": "Mozilla/5.0 (compatible; TrmnlPatentPlugin/1.0)", Accept: "application/json" };
const CDN = "https://patentimages.storage.googleapis.com/";
const MAX_PAGES = 10; // plafond imposé par le moteur : 10 pages x 100
const PER_RUN = parseInt(process.env.PER_RUN || "600", 10);
const DELAY_MS = parseInt(process.env.DELAY_MS || "4000", 10);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** L'article compte : la revendication dit "for an electronic reader", jamais "for a". */
const article = (t) => (/^[aeiou]/i.test(t) ? "an" : "a");

/**
 * Deux modes de collecte :
 *  - "term"     : phrase exacte de la revendication, très précis mais générique.
 *  - "assignee" : par déposant. Indispensable pour les modèles identifiables —
 *                 une PS5 est déposée sous le titre "Game console", on ne peut
 *                 l'atteindre que par Sony Interactive Entertainment.
 * Les deux ne se combinent pas : phrase + déposant renvoie zéro résultat.
 */
async function query(entry, page) {
  const q =
    entry.mode === "assignee"
      ? `assignee=${encodeURIComponent(entry.value)}&country=US&num=100&page=${page}`
      : `q=${encodeURIComponent(`"ornamental design for ${article(entry.value)} ${entry.value}"`)}&country=US&num=100&page=${page}`;
  const r = await fetch("https://patents.google.com/xhr/query?url=" + encodeURIComponent(q), {
    headers: UA,
    signal: AbortSignal.timeout(30000),
  });
  if (r.status === 429 || r.status === 503) throw new Error("THROTTLED");
  if (!r.ok) throw new Error("HTTP " + r.status);
  const j = await r.json();
  const cluster = (j.results && j.results.cluster && j.results.cluster[0]) || {};
  return { total: j.results.total_num_results, results: cluster.result || [] };
}

/** Les résultats arrivent en HTML : entités et ellipse de troncature à nettoyer. */
const clean = (v) =>
  (v || "")
    .replace(/&hellip;/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/<[^>]+>/g, "")
    .replace(/\s+/g, " ")
    .trim();

/** Ne garde que les vrais design patents US, avec au moins une planche. */
function normalize(entry, term) {
  const p = entry.patent || {};
  const num = p.publication_number || "";
  if (!/^USD\d+/.test(num)) return null;
  const figs = (p.figures || []).map((f) => f.full).filter(Boolean);
  if (!figs.length) return null;
  return {
    number: num,
    title: clean(p.title),
    assignee: clean(p.assignee),
    inventor: clean(p.inventor),
    year: parseInt((p.grant_date || p.publication_date || "").slice(0, 4), 10) || null,
    term,
    figures: figs.map((f) => CDN + f),
  };
}

(async () => {
  const terms = JSON.parse(fs.readFileSync(TERMS_FILE, "utf8")).map((v) => ({
    mode: "term",
    value: v,
    key: `t:${v}`,
  }));
  const assignees = fs.existsSync(ASSIGNEES_FILE)
    ? JSON.parse(fs.readFileSync(ASSIGNEES_FILE, "utf8")).map((v) => ({
        mode: "assignee",
        value: v,
        key: `a:${v}`,
      }))
    : [];
  // Entrelacement : sans lui, les déposants (donc les modèles identifiables :
  // PS5, Xbox, Steam Machine) ne seraient atteints qu'après les 115 termes,
  // soit plusieurs jours de collecte.
  const queue = [];
  const ratio = Math.max(1, Math.round(terms.length / Math.max(1, assignees.length)));
  let ti = 0;
  let ai = 0;
  while (ti < terms.length || ai < assignees.length) {
    for (let k = 0; k < ratio && ti < terms.length; k++) queue.push(terms[ti++]);
    if (ai < assignees.length) queue.push(assignees[ai++]);
  }
  const corpus = fs.existsSync(CORPUS) ? JSON.parse(fs.readFileSync(CORPUS, "utf8")) : [];
  const state = fs.existsSync(STATE) ? JSON.parse(fs.readFileSync(STATE, "utf8")) : { done: {}, throttled_at: null };
  const seen = new Set(corpus.map((c) => c.number));

  let added = 0;
  let calls = 0;

  outer: for (const entry of queue) {
    const term = entry.value;
    const from = state.done[entry.key] || state.done[term] || 0;
    if (from === "complete") continue;

    for (let page = from; page < MAX_PAGES; page++) {
      if (added >= PER_RUN) break outer;
      let res;
      try {
        res = await query(entry, page);
        calls++;
      } catch (e) {
        if (e.message === "THROTTLED") {
          console.log(`\n⚠️  Bloqué par le moteur après ${calls} requêtes. Arrêt propre, reprise au prochain run.`);
          state.throttled_at = new Date().toISOString();
          break outer;
        }
        console.log(`  ${term} p${page} : ${e.message}`);
        break;
      }

      let fresh = 0;
      for (const r of res.results) {
        const n = normalize(r, term);
        if (!n || seen.has(n.number)) continue;
        seen.add(n.number);
        corpus.push(n);
        fresh++;
        added++;
      }
      console.log(
        `  ${entry.mode === "assignee" ? "@" : " "}${term.slice(0, 30).padEnd(31)} p${page} · ` +
          `${res.results.length} résultats · ${fresh} nouveaux (total corpus ${corpus.length})`
      );

      state.done[entry.key] = page + 1;
      if (res.results.length < 100 || (page + 1) * 100 >= res.total) {
        state.done[entry.key] = "complete";
        break;
      }
      await sleep(DELAY_MS);
    }
  }

  fs.writeFileSync(CORPUS, JSON.stringify(corpus, null, 1));
  fs.writeFileSync(STATE, JSON.stringify(state, null, 1));

  const complete = Object.values(state.done).filter((v) => v === "complete").length;
  console.log(`\n${added} brevets ajoutés · corpus ${corpus.length} · ${complete}/${queue.length} entrées épuisées · ${calls} requêtes`);
})();
