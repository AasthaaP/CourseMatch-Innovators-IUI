"""Topic labels for every recommendable course: Option A (keyword) vs Option B (embedding), compared on the
gold set before anything is written. No API key needed.

Spec: S5 (Section 11). Owner: Aastha.
Run: python scripts/tag_topics.py [--compare] [--method keyword|embedding]
  default / --compare : run the 11.4 comparison, record it, write the winning method's labels
  --method X          : run the comparison, record it, but write method X's labels (re-run the loser)
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GOLD_PATH = ROOT / "data/taxonomy/gold_topics.json"
PARAMS_PATH = ROOT / "data/taxonomy/embedding_params.json"
COVERAGE_PATH = ROOT / "docs/DATA_COVERAGE.md"
TOPIC_SECTION = "## Topic labelling method comparison"
FLOORS = [round(0.15 + 0.025 * i, 3) for i in range(11)]  # 0.15 .. 0.40
TOP_KS = [4, 6, 8]
MAX_COVERS, MAX_ASSUMES = 8, 5

# Option A dictionary: every taxonomy topic -> match strings (the topic itself plus synonyms).
# Strings match at a word start, so "computer network" also matches "computer networks". Bare generic
# words were audited against the catalog on 2026-11-01 and replaced by specific phrases where they meant
# something else here ("network" in "adversarial networks", "algorithm" in "backpropagation algorithm",
# "cloud" in "point cloud", "radio" in "radiosity", "mobile" in "mobile robots", "logic" in "logic
# synthesis", ...). Bare words kept because every catalog use is on topic: "vision", "image", "speech",
# "agent", "feedback", "signal", "parallel". CSCE 636 (spec 11.5) gets machine learning from "neural
# network", since neural networks are a machine learning method.
SYNONYMS = {
    "algorithms": ["design and analysis of", "analysis of algorithms", "algorithm design", "data structure", "graph algorithm", "sorting", "algorithmic"],
    "complexity theory": ["complexity theory", "computational complexity", "np-complete", "complexity class"],
    "computability": ["computability", "turing machine", "decidab", "automata", "formal language"],
    "randomized algorithms": ["randomized algorithm", "probabilistic algorithm", "randomization", "randomized"],
    "optimization": ["optimization", "convex", "linear programming", "gradient descent", "gradient-based", "optimal load flow", "optimal power flow"],
    "linear algebra": ["linear algebra", "matrix", "matrices", "eigenvalue", "vector space"],
    "probability": ["probability", "probabilistic", "random variable", "stochastic"],
    "statistics": ["statistic", "regression", "estimation", "bayesian", "inference"],
    "discrete mathematics": ["discrete mathematics", "discrete structure", "combinatoric", "graph theory", "propositional logic", "first-order logic", "predicate logic", "mathematical logic"],
    "machine learning": ["machine learning", "supervised learning", "unsupervised learning", "learning algorithm", "learning theory", "statistical learning", "classifier", "neural network"],
    "deep learning": ["deep learning", "neural network", "neural computing", "convolutional"],
    "reinforcement learning": ["reinforcement learning", "markov decision", "reward function", "policy gradient"],
    "natural language processing": ["natural language", "nlp", "language model", "text processing", "linguistic"],
    "computer vision": ["computer vision", "vision", "image understanding", "object recognition", "visual perception"],
    "image processing": ["image processing", "image", "digital image", "photograph"],
    "speech processing": ["speech", "spoken language", "audio processing", "audio signal"],
    "pattern recognition": ["pattern recognition", "pattern analysis", "classification", "clustering"],
    "data mining": ["data mining", "knowledge discovery", "association rule", "data analytic"],
    "information retrieval": ["information retrieval", "search engine", "indexing", "retrieval", "recommender"],
    "data visualization": ["visualization", "visual analytic", "infographic"],
    "databases": ["database", "query language", "sql", "relational model", "relational database", "relational algebra", "transaction"],
    "big data": ["big data", "large-scale data", "massive data", "data-intensive", "mapreduce"],
    "operating systems": ["operating system", "os kernel", "kernel api", "kernel programming", "process scheduling", "virtual memory", "file system"],
    "computer architecture": ["computer architecture", "processor", "microarchitecture", "memory hierarch", "pipelin", "cache", "vlsi", "digital system"],
    "parallel computing": ["parallel", "multicore", "multiprocessor", "concurrent computation", "concurrent system", "concurrency"],
    "distributed systems": ["distributed system", "distributed processing", "distributed computing", "consensus", "replication", "remote procedure"],
    "cloud computing": ["cloud computing", "cloud platform", "cloud service", "cloud-based", "data center", "virtualization", "datacenter"],
    "computer networks": ["computer network", "network protocol", "network design", "network architecture", "networking", "internet", "tcp", "network routing", "routing protocol", "transport protocol", "sensor network", "packet"],
    "wireless systems": ["wireless", "mobile computing", "mobile network", "mobile system", "mobile application", "cellular", "antenna", "radio frequency", "radiofrequency", "radio architecture", "radios"],
    "high performance computing": ["high performance computing", "supercomput", "hpc", "high-performance"],
    "software engineering": ["software engineering", "software development", "software design", "software testing", "requirements engineering", "object oriented", "object-oriented"],
    "programming languages": ["programming language", "type system", "programming language semantics", "formal semantics", "c++", "functional programming"],
    "compilers": ["compiler", "code generation", "parsing", "program analysis"],
    "formal methods": ["formal method", "formal verification", "model checking", "theorem proving"],
    "security": ["security", "secure", "attack", "vulnerabilit", "malware", "cybersecurity"],
    "cryptography": ["cryptograph", "encryption", "cipher", "hash function", "cryptographic"],
    "privacy": ["privacy", "anonymity", "personal data", "differential privacy"],
    "network security": ["network security", "firewall", "intrusion detection", "authentication"],
    "digital forensics": ["forensic", "evidence recovery", "incident response"],
    "robotics": ["robot", "robotic", "manipulator", "motion planning"],
    "autonomous systems": ["autonomous", "self-driving", "unmanned", "autonomy"],
    "control systems": ["control system", "feedback", "controller", "control theory", "control of", "adaptive control", "motion control", "control strateg", "optimal control"],
    "intelligent agents": ["intelligent agent", "multi-agent", "multiple agents", "agent"],
    "human computer interaction": ["human computer interaction", "human-computer", "human-centered", "usability", "user study", "cooperative work", "collaborative", "new media"],
    "user interfaces": ["user interface", "interface design", "interaction technique", "sketch recognition", "sketch-based"],
    "accessibility": ["accessib", "disabilit", "assistive"],
    "virtual reality": ["virtual reality", "augmented reality", "immersive", "virtual environment"],
    "computer graphics": ["computer graphics", "graphics", "rendering", "animation", "special effects", "3-d modeling"],
    "geometric modeling": ["geometric modeling", "geometric model", "curves and surfaces", "spline", "polygon mesh", "mesh generation", "3-d modeling", "sculpting"],
    "computational geometry": ["computational geometry", "convex hull", "voronoi", "geometric algorithm", "geometrical problem"],
    "computational biology": ["computational biology", "biological sequence", "biological data", "systems biology", "genom", "protein"],
    "bioinformatics": ["bioinformatic", "sequence alignment", "biomolecul"],
    "scientific computing": ["scientific computing", "numerical", "numerical simulation", "physical simulation", "computational science", "differential equation"],
    "quantum computing": ["quantum"],
    "signal processing": ["signal processing", "signal", "fourier", "filter", "spectral analysis", "spectral estimation", "spectral domain", "sampling theorem", "data converter", "analog-to-digital", "digital-to-analog", "modulation"],
    "embedded systems": ["embedded", "microcontroller", "real-time system", "cyber-physical"],
    "hardware verification": ["hardware verification", "design verification", "functional verification", "verilog", "testing of digital", "diagnosis of digital", "hardware description language"],
    "game theory": ["game theory", "game-theoretic", "mechanism design", "equilibri"],
}
# Phrases that contain a match string but mean something else; their matches are subtracted.
EXCLUDE = {
    "pattern recognition": ["graduate classification", "senior classification", "junior classification"],
    "parallel computing": ["parallel i/o"],  # interfacing, not parallel computing
    "control systems": ["control of digital systems"],  # microprogrammed control, not control theory
}
_word = lambda s: re.compile(r"(?<![a-z0-9])" + re.escape(s))  # noqa: E731
_PATTERNS = {t: [_word(s) for s in strs] for t, strs in SYNONYMS.items()}
_EXCLUDE = {t: [_word(s) for s in strs] for t, strs in EXCLUDE.items()}


def keyword_topics(text: str, k: int) -> list[str]:
    """Option A: rank matched topics by total occurrences of their strings; keep the top k."""
    text = text.lower()
    counts = {t: sum(len(p.findall(text)) for p in pats) - sum(len(p.findall(text)) for p in _EXCLUDE.get(t, []))
              for t, pats in _PATTERNS.items()}
    hits = [t for t, n in counts.items() if n > 0]
    return sorted(hits, key=lambda t: -counts[t])[:k]


def embedding_topics(sims, taxonomy, top_k, floor, cap=None) -> list[str]:
    """Option B, spec 11.2: top_k by cosine, kept only above the floor."""
    order = sims.argsort()[::-1][: min(top_k, cap or top_k)]
    return [taxonomy[i] for i in order if sims[i] >= floor]


def micro_prf(pred: dict, gold: dict, codes) -> tuple[float, float, float]:
    inter = sum(len(set(pred[c]) & set(gold[c])) for c in codes)
    p_n = sum(len(pred[c]) for c in codes)
    g_n = sum(len(gold[c]) for c in codes)
    p = inter / p_n if p_n else 0.0
    r = inter / g_n if g_n else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def assumes_text(code, db, by_code) -> str:
    """Prerequisite fragments that name courses or are unparsed (classification and approval fragments say
    nothing about background) plus the titles and descriptions of the courses named in course groups."""
    from sqlalchemy import select

    from backend.app.models import PrereqGroup

    parts = []
    for g in db.scalars(select(PrereqGroup).where(PrereqGroup.course_code == code)):
        if g.kind in ("course", "unparsed"):
            parts.append(g.raw_text)
        for alt in json.loads(g.alternatives):
            if alt in by_code:
                parts.append(f"{by_code[alt].title}. {by_code[alt].description}")
    return " ".join(parts)


def decide(a: dict, b: dict) -> tuple[str, str]:
    """Spec 11.4 Step 3."""
    disq = {}
    for name, m in (("keyword", a), ("embedding", b)):
        if m["coverage"] < 0.90:
            disq[name] = f"coverage {m['coverage']:.2f} below 0.90"
        elif m["mean_labels"] > 10:
            disq[name] = f"mean_labels {m['mean_labels']:.1f} above 10"
    if len(disq) == 1:
        loser = next(iter(disq))
        winner = "embedding" if loser == "keyword" else "keyword"
        return winner, f"Option {'A' if loser == 'keyword' else 'B'} disqualified: {disq[loser]}."
    # Both disqualified is a case Step 3 does not cover: fall back to the F1 rules and say so.
    note = ("Both options are disqualified (A: {}; B: {}), which Step 3 does not cover, so the F1 rules "
            "decide. ".format(disq["keyword"], disq["embedding"]) if len(disq) == 2 else "")
    if a["f1"] - b["f1"] > 0.05:
        return "keyword", note + f"Option A test F1 higher by {a['f1'] - b['f1']:.3f} (> 0.05)."
    if b["f1"] - a["f1"] > 0.05:
        return "embedding", note + f"Option B test F1 higher by {b['f1'] - a['f1']:.3f} (> 0.05)."
    return "embedding", note + f"Test F1 within 0.05 ({a['f1']:.3f} vs {b['f1']:.3f}); the tie goes to Option B."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true", help="run the comparison (always runs before writing)")
    ap.add_argument("--method", choices=["keyword", "embedding"], help="write this method's labels")
    args = ap.parse_args()

    from backend.app.config import EMBEDDING_DEVICE, EMBEDDING_MODEL  # sets OpenMP env first
    from sentence_transformers import SentenceTransformer
    from sqlalchemy import delete, select

    from backend.app.db import SessionLocal, init_db
    from backend.app.models import Course, CourseTopic
    from backend.app.topics import load_taxonomy

    init_db()
    taxonomy = load_taxonomy()
    assert set(SYNONYMS) == set(taxonomy), set(SYNONYMS) ^ set(taxonomy)
    gold_file = json.loads(GOLD_PATH.read_text())
    gold = {c: v["covers"] for c, v in gold_file.items() if not c.startswith("_")}
    tune = sorted(c for c, v in gold_file.items() if not c.startswith("_") and v["split"] == "tune")
    test = sorted(c for c, v in gold_file.items() if not c.startswith("_") and v["split"] == "test")
    reviewed = "not yet reviewed" if "not yet reviewed" in gold_file.get("_status", "") else "Aastha Patel"

    with SessionLocal() as db:
        by_code = {c.code: c for c in db.scalars(select(Course))}
        rec = sorted(c for c, v in by_code.items() if v.is_recommendable)
        texts = {c: f"{by_code[c].title}. {by_code[c].description}" for c in rec}
        a_texts = {c: assumes_text(c, db, by_code) for c in rec}

        model = SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_DEVICE)
        topic_vecs = model.encode(taxonomy, normalize_embeddings=True)
        sims = dict(zip(rec, model.encode([texts[c] for c in rec], normalize_embeddings=True) @ topic_vecs.T))
        a_codes = [c for c in rec if a_texts[c].strip()]
        a_sims = dict(zip(a_codes, model.encode([a_texts[c] for c in a_codes], normalize_embeddings=True) @ topic_vecs.T)) if a_codes else {}

        # Step 1: tune Option B on the tuning half only.
        best = None
        for floor in FLOORS:
            for k in TOP_KS:
                pred = {c: embedding_topics(sims[c], taxonomy, k, floor) for c in tune}
                f1 = micro_prf(pred, gold, tune)[2]
                if best is None or f1 > best[0]:
                    best = (f1, floor, k)
        _, FLOOR, TOP_K = best

        # Step 2: score both on the test half, coverage and mean_labels over all recommendable courses.
        covers_a = {c: keyword_topics(f"{by_code[c].title} {by_code[c].description}", MAX_COVERS) for c in rec}
        covers_b = {c: embedding_topics(sims[c], taxonomy, TOP_K, FLOOR) for c in rec}

        def metrics(covers):
            p, r, f1 = micro_prf(covers, gold, test)
            return {"precision": p, "recall": r, "f1": f1,
                    "coverage": sum(bool(covers[c]) for c in rec) / len(rec),
                    "mean_labels": sum(len(covers[c]) for c in rec) / len(rec)}

        ma, mb = metrics(covers_a), metrics(covers_b)
        winner, reason = decide(ma, mb)
        method = args.method or winner
        other = "embedding" if method == "keyword" else "keyword"

        def assumes_for(m, c, covers):
            if m == "keyword":
                found = keyword_topics(a_texts[c], MAX_COVERS) if a_texts[c].strip() else []
            else:
                found = embedding_topics(a_sims[c], taxonomy, TOP_K, FLOOR, cap=MAX_ASSUMES) if c in a_sims else []
            return [t for t in found if t not in covers][:MAX_ASSUMES]  # background, not what it teaches

        labels = {m: {c: (cov[c], assumes_for(m, c, cov[c])) for c in rec}
                  for m, cov in (("keyword", covers_a), ("embedding", covers_b))}
        effective = sum(bool(labels[method][c][0] or labels[other][c][0]) for c in rec) / len(rec)
        uncovered = [c for c in rec if not (labels[method][c][0] or labels[other][c][0])]

        PARAMS_PATH.write_text(json.dumps({"FLOOR": FLOOR, "TOP_K": TOP_K, "selected_method": winner,
                                           "tuned_on": "tune half of data/taxonomy/gold_topics.json",
                                           "tune_f1": round(best[0], 4)}, indent=2) + "\n")
        table = "\n".join([
            TOPIC_SECTION, "",
            f"Gold set: {len(gold)} courses, {len(tune)} tune / {len(test)} test. Reviewed by: {reviewed}",
            *(["", "**Deviation from spec 11.3:** the tune/test split is interleaved within each department by "
               "sorted code instead of first 10 / last 10, so both halves hold CSCE and ECEN courses "
               f"(tune: {', '.join(tune)}; test: {', '.join(test)}). Team decision 2026-11-01."]
              if tune != sorted(gold)[: len(tune)] else []),
            *(["", "**Provisional:** the gold set has not been reviewed yet, so these numbers may change."]
              if reviewed == "not yet reviewed" else []),
            "", "```",
            f"Option B tuned parameters: FLOOR={FLOOR}, TOP_K={TOP_K}  (tune-half F1 {best[0]:.3f})", "",
            "                  precision  recall    F1    coverage  mean_labels",
            *(f"{name:18s}{m['precision']:8.2f}{m['recall']:8.2f}{m['f1']:8.2f}{m['coverage']:10.2f}{m['mean_labels']:13.1f}"
              for name, m in (("Option A keyword", ma), ("Option B embedding", mb))),
            "", f"Selected: Option {'A' if winner == 'keyword' else 'B'}", f"Reason: {reason}", "```", "",
            f"Both options' labels are stored (`source` column). `backend/app/topics.py` reads the selected option "
            f"first and the other option only where the selected one has no label (spec 11.6), giving an effective "
            f"coverage of {effective:.2f} over the {len(rec)} recommendable courses.",
            "", f"Recommendable courses with no topic from either option ({len(uncovered)}): "
            + (", ".join(uncovered) if uncovered else "none") + ". These are electrical engineering subjects "
            "(circuits, power, electromagnetics, devices, energy) that the fixed 58-topic taxonomy does not name.",
            "", *([f"**Coverage is below 0.90 for both options (A {ma['coverage']:.2f}, B {mb['coverage']:.2f}; "
                   f"{effective:.2f} combined), so spec 11.4 disqualifies both and S5 acceptance item 4 (every "
                   "recommendable course has a covers topic) is not met.** The taxonomy is kept fixed by team "
                   "decision; these courses rank on retrieval similarity, degree fit and readiness only."]
                  if min(ma["coverage"], mb["coverage"]) < 0.90 else []),
            "",
        ])
        print(table)
        old = COVERAGE_PATH.read_text() if COVERAGE_PATH.exists() else ""
        COVERAGE_PATH.parent.mkdir(parents=True, exist_ok=True)  # docs/ is not in git; fresh clones lack it
        COVERAGE_PATH.write_text((old[: old.index(TOPIC_SECTION)] if TOPIC_SECTION in old else old.rstrip() + "\n\n") + table)

        # Step 4: write labels. Both options are stored; the selected one (or --method) is preferred on read.
        rows = [CourseTopic(course_code=c, topic=tp, role=role, source=m)
                for m in (method, other) for c in rec
                for role, topics in (("covers", labels[m][c][0]), ("assumes", labels[m][c][1])) for tp in topics]
        db.execute(delete(CourseTopic).where(CourseTopic.source.in_(["keyword", "embedding"])))
        db.add_all(rows)
        db.commit()
        for m in (method, other):
            n_cov = sum(r.role == "covers" and r.source == m for r in rows)
            n_ass = sum(r.role == "assumes" and r.source == m for r in rows)
            print(f"Wrote {n_cov} covers and {n_ass} assumes rows with source='{m}'")
        for c in ("CSCE 636", "CSCE 633", "CSCE 662", "CSCE 630"):
            print(f"  {c} ({method}): covers {labels[method][c][0]} assumes {labels[method][c][1]}")


if __name__ == "__main__":
    main()
