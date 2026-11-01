#!/usr/bin/env python3
"""
Deterministic Research Quality Gate, Cite-Checker & Anti-Slop Auditor (`audit_report.py` v3.3)
Enforces:
1. Map-Before-Reduce Verification: Every verified raw source in `01_raw_sources/` must have a corresponding
   deep extraction note in `02_extracted_notes/`.
2. Syndication & Source Independence Audit (Union-Find + Shingle Jaccard):
   - Clusters near-duplicate or syndicated copies (`Jaccard >= 0.65`, canonical URL identity, wire-service headers)
     so 5 reprints of 1 press release count as 1 independent source.
3. Proportional Depth & Schema Verification:
   - Extraction notes must include at least 6 `## ` analytical sections, concrete fenced code/prompt blocks,
     and failure-mode analysis.
4. Playbook Completeness: Playbooks in `03_playbooks/` must contain multi-line code/prompt blocks (` ``` `),
   architecture diagrams or tables, and failure-mode/gotcha remediation.
5. Citation Integrity, Quote Verification & Numerical Grounding (Hyperresearch-grade Gate):
   - Resolves every inline citation (`[#N]` or `[yt_*/web_*/gh_*/rd_*]`) against the manifest and Evidence Audit Table;
     unresolved/fabricated citations block the gate.
   - Verifies sentence-level citation bindings (`citation_binding_accuracy_pct`).
   - Checks verbatim English quotes (`>= 6` words) and traces specific technical numbers/quotas/versions/percentages
     in `00_MASTER_REPORT.md` back to `01_raw_sources/` and `02_extracted_notes/` (`numerical_grounding_pct`).
6. Anti-Slop Scanner (Vietnamese & English): Rejects reports containing lazy placeholders, vague hand-waving,
   or word-padding meta-commentary.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

FORBIDDEN_SLOP_PATTERNS = [
    (r"\bcấu hình cho phù hợp\b", "Vague instruction ('cấu hình cho phù hợp') — specify exact parameters/values."),
    (r"\btùy theo nhu cầu(?: của bạn)?\b", "Lazy hand-waving ('tùy theo nhu cầu') — state concrete decision criteria."),
    (r"\bbạn có thể tự tìm hiểu thêm\b", "Delegating research back to user ('bạn có thể tự tìm hiểu thêm')."),
    (r"\bxem chi tiết tại video\b", "Pointer-only summary ('xem chi tiết tại video') — extract the actual steps."),
    (r"\bv\.v\. và v\.v\.\b", "Lazy ellipsis ('v.v. và v.v.') — list the concrete items."),
    (r"\bconfigure as appropriate\b", "Vague instruction ('configure as appropriate') — give exact config."),
    (r"\bit is important to note that\b", "Unslop Rule 23 filler ('it is important to note that')."),
    (r"\bneedless to say\b|\bin conclusion, it is clear\b", "AI throat-clearing filler phrase."),
    (r"\bdelve into\b|\btestament to\b|\btapestry of\b", "Unslop Rule 7 AI vocabulary ('delve/testament/tapestry')."),
    (r"\[TODO\]|\bTBD\b|\bFIXME\b", "Unfinished placeholder ([TODO] / TBD / FIXME)."),
    (
        r"\bwill be (?:refreshed|revisited|updated) as (?:new|more|additional) sources\b",
        "Word-padding meta-commentary ('will be refreshed/updated as new sources...') — delete filler sentence.",
    ),
    (
        r"\bas (?:more|additional)?\s*transcripts become available\b",
        "Word-padding meta-commentary ('as transcripts become available') — delete filler sentence.",
    ),
    (
        r"\bas new sources are (?:ingested|added to the corpus)\b|\bas the evidence base grows\b",
        "Word-padding meta-commentary ('as new sources are added / evidence base grows') — delete filler sentence.",
    ),
    (
        r"\bstored under `?01_raw_sources/keyframes\b",
        "Lazy pointer to keyframes directory ('stored under 01_raw_sources/keyframes') — embed the image inline with ![caption](path) instead.",
    ),
]

WIRE_MARKERS = (
    "prnewswire",
    "pr newswire",
    "business wire",
    "businesswire",
    "globe newswire",
    "globenewswire",
    "accesswire",
    "newsfile corp",
)
_TRACKING_PARAMS_RE = re.compile(r"^(utm_|fbclid|gclid|ref$|source$)")
NEAR_DUP_THRESHOLD = 0.65


def canonical_url(url: str) -> str:
    """Normalize scheme/host/path/query so syndication mirrors collide."""
    if not url:
        return ""
    p = urlparse(url.strip().lower())
    host = p.netloc.removeprefix("www.")
    path = p.path.rstrip("/")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(p.query) if not _TRACKING_PARAMS_RE.match(k)))
    return urlunparse(("https", host, path, "", query, ""))


def _shingle_set(text: str, k: int = 5) -> Set[int]:
    """Compute hashed k-word shingles over normalized body text."""
    words = re.findall(r"[a-z0-9]{2,}", (text or "").lower())
    if len(words) < k:
        return {hash(" ".join(words))} if words else set()
    # Sample up to first 2,500 words for fast deterministic shingle comparison
    words = words[:2500]
    return {hash(" ".join(words[i : i + k])) for i in range(len(words) - k + 1)}


def _jaccard(a: Set[int], b: Set[int]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _wire_signature(body: str) -> str:
    head = (body or "")[:1500].lower()
    marker = next((m for m in WIRE_MARKERS if m in head), None)
    if not marker:
        return ""
    tokens = re.findall(r"[a-z0-9]{4,}", head)[:10]
    return f"{marker}|{' '.join(tokens)}"


def compute_source_independence(verified_sources: List[Dict[str, Any]], ws: Path) -> Dict[str, Any]:
    """
    Clusters derivative/syndicated sources via Union-Find across:
    1. Canonical URL identity
    2. Wire-service press release signature
    3. 5-gram Shingle Jaccard similarity >= 0.65
    """
    parent: Dict[str, str] = {}
    cluster_kind: Dict[Tuple[str, str], str] = {}
    shingles: Dict[str, Set[int]] = {}
    urls_by_id: Dict[str, str] = {}
    wires_by_id: Dict[str, str] = {}

    for src in verified_sources:
        sid = src.get("id", "unknown")
        parent[sid] = sid
        urls_by_id[sid] = canonical_url(src.get("url", ""))
        raw_rel = src.get("raw_path") or f"01_raw_sources/{sid}.md"
        raw_path = ws / raw_rel
        body = ""
        if raw_path.exists():
            full_raw = raw_path.read_text(encoding="utf-8", errors="replace")
            # Strip metadata header before section 3
            parts = re.split(r"^##\s+3\.", full_raw, maxsplit=1, flags=re.MULTILINE)
            body = parts[1] if len(parts) > 1 else full_raw
        shingles[sid] = _shingle_set(body)
        wires_by_id[sid] = _wire_signature(body)

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str, kind: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
            cluster_kind[(min(a, b), max(a, b))] = kind

    ids = list(parent.keys())
    # 1. URL identity
    by_url: Dict[str, List[str]] = {}
    for sid in ids:
        u = urls_by_id[sid]
        if u:
            by_url.setdefault(u, []).append(sid)
    for group in by_url.values():
        for other in group[1:]:
            union(group[0], other, "canonical_url")

    # 2. Wire signature
    by_wire: Dict[str, List[str]] = {}
    for sid in ids:
        w = wires_by_id[sid]
        if w:
            by_wire.setdefault(w, []).append(sid)
    for group in by_wire.values():
        for other in group[1:]:
            union(group[0], other, "wire_reprint")

    # 3. Shingle Jaccard similarity
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if find(a) == find(b):
                continue
            if _jaccard(shingles[a], shingles[b]) >= NEAR_DUP_THRESHOLD:
                union(a, b, "near_duplicate_body")

    groups: Dict[str, List[str]] = {}
    for sid in ids:
        groups.setdefault(find(sid), []).append(sid)

    clusters = []
    for root, members in groups.items():
        if len(members) > 1:
            clusters.append(
                {
                    "root": root,
                    "duplicates": [m for m in members if m != root],
                    "cluster_size": len(members),
                }
            )

    return {
        "independent_sources_count": len(groups),
        "duplicate_clusters_count": len(clusters),
        "syndication_clusters": clusters,
    }


def scan_file_for_slop(md_path: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    if not md_path.exists():
        return issues
    lines = md_path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_code_block = False
    for idx, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        for pat, reason in FORBIDDEN_SLOP_PATTERNS:
            if re.search(pat, line, re.IGNORECASE):
                issues.append(
                    {
                        "file": md_path.name,
                        "line": idx,
                        "reason": reason,
                        "excerpt": line.strip()[:140],
                    }
                )
    return issues


def compute_required_note_words(raw_word_count: int) -> int:
    """Low anti-stub floor."""
    if raw_word_count <= 800:
        return 90
    return 140


def compute_saturation_metrics(verified_sources: List[Dict[str, Any]], ws: Path) -> Dict[str, Any]:
    """
    Computes empirical Information Saturation & Volume Metrics across ingested sources.
    """
    total_raw_words = sum(int(s.get("word_count") or 0) for s in verified_sources)
    equiv_pages = round(total_raw_words / 250.0, 1)

    ordered = sorted(verified_sources, key=lambda x: int(x.get("word_count") or 0), reverse=True)
    note_term_sets: List[set] = []

    for s in ordered:
        sid = s.get("id", "unknown")
        note_rel = s.get("extracted_note_path") or f"02_extracted_notes/{sid}_note.md"
        note_path = ws / note_rel
        if not note_path.exists():
            continue
        txt = note_path.read_text(encoding="utf-8", errors="replace")
        backtick_terms = {t.lower().strip() for t in re.findall(r"`([A-Za-z0-9_./:-]{3,35})`", txt)}
        proper_terms = {t.lower() for t in re.findall(r"\b[A-Z][A-Za-z0-9_-]{3,25}\b", txt)}
        combined = {t for t in (backtick_terms | proper_terms) if not t.isdigit()}
        if combined:
            note_term_sets.append(combined)

    if len(note_term_sets) < 4:
        return {
            "total_raw_words": total_raw_words,
            "equivalent_book_pages": equiv_pages,
            "saturation_score_pct": 0.0,
            "status": "INSUFFICIENT_SOURCES_FOR_SATURATION_CURVE",
        }

    split_idx = max(2, int(len(note_term_sets) * 0.75))
    core_vocab = set().union(*note_term_sets[:split_idx])
    tail_vocab = set().union(*note_term_sets[split_idx:])

    term_freq: Dict[str, int] = {}
    for ts in note_term_sets:
        for term in ts:
            term_freq[term] = term_freq.get(term, 0) + 1
    domain_tail = {t for t in tail_vocab if term_freq.get(t, 0) >= 2}

    if not domain_tail:
        saturation_pct = 90.0
    else:
        already_known = len(domain_tail & core_vocab)
        saturation_pct = round((already_known / len(domain_tail)) * 100.0, 1)

    is_saturated = saturation_pct >= 80.0 and total_raw_words >= 30000
    return {
        "total_raw_words": total_raw_words,
        "equivalent_book_pages": equiv_pages,
        "saturation_score_pct": saturation_pct,
        "status": "SATURATED_HIGH_CONFIDENCE" if is_saturated else "EXPAND_SNOWBALL_RECOMMENDED",
    }


def _build_corpus_text_by_source(verified_sources: List[Dict[str, Any]], ws: Path) -> Dict[str, str]:
    """Load combined text (raw source + extracted note + title/url) per source ID."""
    corpus_by_id: Dict[str, str] = {}
    for s in verified_sources:
        sid = s.get("id", "")
        if not sid:
            continue
        chunks = [str(s.get("title") or ""), str(s.get("url") or "")]
        raw_rel = s.get("raw_path") or f"01_raw_sources/{sid}.md"
        note_rel = s.get("extracted_note_path") or f"02_extracted_notes/{sid}_note.md"
        for rel in (raw_rel, note_rel):
            p = ws / rel
            if p.exists():
                chunks.append(p.read_text(encoding="utf-8", errors="replace"))
        corpus_by_id[sid] = "\n".join(chunks).lower()
    return corpus_by_id


def _parse_numbered_citation_map(report_text: str, verified_sources: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Map `[#N]` -> `source_id` by scanning table rows or list entries in `00_MASTER_REPORT.md`
    (e.g. `| `#1` | `yt_4hKJ9X6rGFo` |` or `[#1] ... yt_...`), falling back to 1-based index in `verified_sources`.
    """
    known_ids = {s.get("id", "") for s in verified_sources if s.get("id")}
    mapping: Dict[str, str] = {}

    for line in report_text.splitlines():
        num_m = re.search(r"#(\d{1,3})\b", line)
        if not num_m:
            continue
        num = num_m.group(1)
        id_m = re.search(r"\b((?:yt|web|gh|rd)_[A-Za-z0-9_-]+)\b", line)
        if id_m and id_m.group(1) in known_ids:
            mapping[num] = id_m.group(1)

    for idx, s in enumerate(verified_sources, start=1):
        num = str(idx)
        if num not in mapping and s.get("id"):
            mapping[num] = s["id"]

    return mapping


def audit_citations_quotes_and_numbers(
    report_text: str,
    verified_sources: List[Dict[str, Any]],
    ws: Path,
) -> Dict[str, Any]:
    """
    Hyperresearch-grade Verification Battery:
    1. Citation Resolution & Sentence-Citation Binding (`citecheck`):
       - Verifies that every `[#N]` or `[yt_*/web_*/gh_*/rd_*]` inline marker resolves to a real source in `sources_manifest.json`.
       - Checks whether technical tokens/numbers in each cited sentence appear in the cited source's text (`citation_binding_accuracy_pct`).
    2. Verbatim Quote Integrity (`quote-integrity`):
       - Scans English verbatim quotes (`>= 6` ASCII words outside code blocks) and checks that their content words exist in the corpus.
    3. Numerical Grounding (`numeric-consistency`):
       - Extracts substantive technical numbers (versions `0.60.0`, percentages `98.4%`, dollar amounts `$200`, specific counts `145,906`)
         from the report body and verifies what percentage are directly traceable to `01_raw_sources/` + `02_extracted_notes/`.
    """
    corpus_by_id = _build_corpus_text_by_source(verified_sources, ws)
    full_corpus_blob = "\n".join(corpus_by_id.values())
    full_corpus_no_commas = full_corpus_blob.replace(",", "")
    known_ids = set(corpus_by_id.keys())
    num_map = _parse_numbered_citation_map(report_text, verified_sources)

    # Strip fenced code blocks and the final Evidence Audit Table section for prose scanning
    prose_without_code = re.sub(r"```.*?```", "", report_text, flags=re.DOTALL)
    body_split = re.split(
        r"^##\s+(?:10\.|6\.)?\s*(?:Những chỗ mâu thuẫn|Evidence Audit Table|Bảng Kiểm toán Bằng chứng)",
        prose_without_code,
        maxsplit=1,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    narrative_prose = body_split[0] if body_split else prose_without_code

    # 1. Citation Resolution & Sentence Binding
    unresolved_citations: List[str] = []
    total_bindings = 0
    supported_bindings = 0

    for line in narrative_prose.splitlines():
        if not line.strip() or line.strip().startswith("|---"):
            continue
        # Find all citation brackets on this line
        cite_matches = list(
            re.finditer(r"\[(?:#(\d{1,3})|((?:yt|web|gh|rd)_[A-Za-z0-9_-]+))(?:\s*[,;][^\]]*)?\]", line)
        )
        if not cite_matches:
            continue

        # Extract technical tokens and numbers from the line
        line_Tech_tokens = {
            t.lower()
            for t in re.findall(r"`([A-Za-z0-9_./:-]{3,30})`|\b([A-Z][A-Za-z0-9_-]{3,25})\b", line)
            for t in t
            if t and len(t) >= 3
        }
        line_numbers = {n.replace(",", "") for n in re.findall(r"\b\d+(?:\.\d+)?%?\b", line)}

        for m in cite_matches:
            num_id, direct_id = m.group(1), m.group(2)
            resolved_id = None
            raw_marker = m.group(0)
            if direct_id:
                if direct_id in known_ids:
                    resolved_id = direct_id
                else:
                    # Try prefix match in case ID was slightly truncated in prose
                    prefix_hits = [kid for kid in known_ids if kid.startswith(direct_id[:20])]
                    resolved_id = prefix_hits[0] if prefix_hits else None
            elif num_id:
                resolved_id = num_map.get(num_id)

            if not resolved_id or resolved_id not in corpus_by_id:
                unresolved_citations.append(raw_marker)
                continue

            total_bindings += 1
            src_blob = corpus_by_id[resolved_id]
            src_blob_no_commas = src_blob.replace(",", "")

            # Check if at least one technical token or number from the line appears in the cited source
            token_hit = any(tok in src_blob for tok in line_Tech_tokens) if line_Tech_tokens else True
            num_hit = any(num in src_blob_no_commas for num in line_numbers) if line_numbers else False
            if token_hit or num_hit:
                supported_bindings += 1

    binding_accuracy_pct = round((supported_bindings / total_bindings) * 100.0, 1) if total_bindings > 0 else 100.0

    # 2. Quote Integrity (check English verbatim quotes >= 6 words that are not translated Vietnamese)
    unverified_quotes: List[str] = []
    for qm in re.finditer(r'["“]([^"“”\n]{25,300})["”]', narrative_prose):
        q_text = qm.group(1).strip()
        words = re.findall(r"[A-Za-z]{3,}", q_text)
        # Only check quotes that are pure ASCII English (>= 6 words, no Vietnamese diacritics)
        if len(words) < 6 or any(ord(c) > 127 for c in q_text):
            continue
        sig_words = [w.lower() for w in words if len(w) >= 4]
        if not sig_words:
            continue
        matched_w = sum(1 for w in sig_words if w in full_corpus_blob)
        if (matched_w / len(sig_words)) < 0.6:
            unverified_quotes.append(q_text[:100])

    # 3. Numerical Grounding (trace specific technical numbers in report back to corpus)
    # Match percentages (98.4%), dollar figures ($200), semantic versions (0.60.0), or specific 3+ digit numbers
    raw_nums = re.findall(
        r"\$\d[\d,.]*|\b\d+\.\d+\.\d+\b|\b\d+(?:\.\d+)?%|\b\d{1,3}(?:,\d{3})+\b|\b\d{3,6}\b",
        narrative_prose,
    )
    ignore_nums = {"100", "100%", "200", "300", "500", "1000", "2024", "2025", "2026", "2027"}
    candidate_nums = sorted({n.strip(".,") for n in raw_nums if n.strip(".,") not in ignore_nums})

    traced_nums: List[str] = []
    untraced_nums: List[str] = []
    for n in candidate_nums:
        clean_n = n.lstrip("$").rstrip("%").replace(",", "")
        # Also normalize Vietnamese thousand-separator dots (e.g. $10.000 -> 10000)
        vn_clean_n = re.sub(r"^(\d{1,3})\.(\d{3})$", r"\1\2", clean_n)
        if (
            clean_n in full_corpus_no_commas
            or vn_clean_n in full_corpus_no_commas
            or n.lower() in full_corpus_blob
        ):
            traced_nums.append(n)
        else:
            untraced_nums.append(n)

    num_grounding_pct = (
        round((len(traced_nums) / len(candidate_nums)) * 100.0, 1) if candidate_nums else 100.0
    )

    return {
        "total_citation_bindings_checked": total_bindings,
        "unresolved_citations": sorted(set(unresolved_citations)),
        "citation_binding_accuracy_pct": binding_accuracy_pct,
        "unverified_english_quotes": unverified_quotes[:5],
        "technical_numbers_checked": len(candidate_nums),
        "numerical_grounding_pct": num_grounding_pct,
        "untraced_numbers_sample": untraced_nums[:10],
    }


def audit_workspace(ws: Path, min_sources: int, min_playbooks: int) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    slop_hits: List[Dict[str, Any]] = []

    manifest_path = ws / "01_raw_sources" / "sources_manifest.json"
    notes_dir = ws / "02_extracted_notes"
    playbooks_dir = ws / "03_playbooks"
    master_report = ws / "00_MASTER_REPORT.md"
    audit_tsv = ws / "audit_trail.tsv"

    if not manifest_path.exists():
        errors.append("Missing 01_raw_sources/sources_manifest.json (No raw sources ingested).")
        sources = []
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            sources = manifest.get("sources") or []
        except Exception as e:
            errors.append(f"Corrupt sources_manifest.json: {e}")
            sources = []

    verified_sources = [
        s
        for s in sources
        if str(s.get("evidence_level", "")).startswith("FULL_") and int(s.get("word_count") or 0) >= 80
    ]
    zero_word_yt = [
        s.get("id")
        for s in sources
        if s.get("kind") == "youtube" and int(s.get("word_count") or 0) < 50
    ]
    if zero_word_yt:
        warnings.append(
            f"{len(zero_word_yt)} YouTube video(s) had 0 transcript words ({', '.join(zero_word_yt[:5])}) and were excluded from verified_full_sources."
        )

    # Syndication & Independence Audit
    ind_metrics = compute_source_independence(verified_sources, ws)
    independent_count = ind_metrics["independent_sources_count"]

    if independent_count < min_sources:
        errors.append(
            f"Independent verified sources count ({independent_count} independent out of {len(verified_sources)} total) is below minimum threshold ({min_sources})."
        )
    if ind_metrics["duplicate_clusters_count"] > 0:
        warnings.append(
            f"Syndication/Independence audit grouped {ind_metrics['duplicate_clusters_count']} near-duplicate source cluster(s)."
        )

    # Check 1-to-1 Map extraction notes with proportional depth & schema enforcement
    missing_notes: List[str] = []
    shallow_notes: List[str] = []
    incomplete_schema_notes: List[str] = []

    for src in verified_sources:
        sid = src.get("id", "unknown")
        raw_wc = int(src.get("word_count") or 0)
        req_wc = compute_required_note_words(raw_wc)
        note_rel = src.get("extracted_note_path") or f"02_extracted_notes/{sid}_note.md"
        note_path = ws / note_rel

        if not note_path.exists():
            missing_notes.append(f"{sid} -> expected {note_rel}")
        else:
            txt = note_path.read_text(encoding="utf-8", errors="replace")
            wc = len(txt.split())
            if wc < req_wc:
                shallow_notes.append(
                    f"{note_rel} is a stub — extract concrete commands, prompts, or failure modes from the raw source (NEVER pad prose or count words)"
                )

            h2_count = len(re.findall(r"^##\s+", txt, flags=re.MULTILINE))
            if h2_count < 6:
                incomplete_schema_notes.append(
                    f"{note_rel} (only {h2_count} '##' sections; expected >= 6 from 10-dimension schema)"
                )

            if raw_wc >= 1500 and "```" not in txt:
                incomplete_schema_notes.append(f"{note_rel} (missing fenced ``` prompt/command/config block)")

            slop_hits.extend(scan_file_for_slop(note_path))

    if missing_notes:
        errors.append(
            f"Map-Before-Reduce violation: {len(missing_notes)} verified source(s) lack extraction notes in 02_extracted_notes/: "
            + ", ".join(missing_notes[:5])
        )
    if shallow_notes:
        errors.append(
            "Incomplete extraction note(s) in 02_extracted_notes/: " + "; ".join(shallow_notes[:5])
        )
    if incomplete_schema_notes:
        errors.append(
            "Extraction schema violation in 02_extracted_notes/: " + "; ".join(incomplete_schema_notes[:5])
        )

    # Check Playbooks (Artifact Density over Word Count)
    playbook_files = sorted(playbooks_dir.glob("*.md")) if playbooks_dir.exists() else []
    if len(playbook_files) < min_playbooks:
        errors.append(
            f"Modular playbooks in 03_playbooks/ ({len(playbook_files)}) is below minimum required ({min_playbooks})."
        )

    for pb in playbook_files:
        pb_txt = pb.read_text(encoding="utf-8", errors="replace")
        pb_wc = len(pb_txt.split())
        pb_h2 = len(re.findall(r"^##\s+", pb_txt, flags=re.MULTILINE))
        if pb_wc < 180 or pb_h2 < 5:
            errors.append(
                f"Playbook '{pb.name}' is missing required Diátaxis sections (found {pb_h2}/5 '##' sections). Add concrete setup steps, code/prompt blocks, or failure-mode tables — do NOT pad prose."
            )
        if "```" not in pb_txt:
            errors.append(
                f"Playbook '{pb.name}' lacks concrete code/prompt/config blocks (no fenced ``` block found)."
            )
        else:
            pb_blocks = re.findall(r"```(?!mermaid)\w*\n(.*?)```", pb_txt, flags=re.DOTALL)
            multiline_pb_blocks = [
                b for b in pb_blocks if len([ln for ln in b.strip().splitlines() if ln.strip()]) >= 3
            ]
            if not multiline_pb_blocks:
                errors.append(
                    f"Playbook '{pb.name}' only contains 1-line stub code blocks. Include at least one multi-line (>= 3 lines) verbatim System Prompt, Skill definition, or config block."
                )
        slop_hits.extend(scan_file_for_slop(pb))

    # Check Master Report (Structural & Artifact Density + Cite-Check & Numerical Grounding)
    master_wc = 0
    cite_verification: Dict[str, Any] = {}
    keyframes_dir = ws / "01_raw_sources" / "keyframes"
    available_keyframes = (
        list(keyframes_dir.glob("*.jpg")) + list(keyframes_dir.glob("*.png"))
        if keyframes_dir.exists()
        else []
    )

    if not master_report.exists():
        errors.append("Missing 00_MASTER_REPORT.md in workspace root.")
    else:
        m_txt = master_report.read_text(encoding="utf-8", errors="replace")
        master_wc = len(m_txt.split())
        master_h2 = len(re.findall(r"^##\s+", m_txt, flags=re.MULTILINE))
        table_sep_count = len(re.findall(r"^\s*\|?\s*:?-{3,}:?\s*\|", m_txt, flags=re.MULTILINE))
        if master_wc < 600 or master_h2 < 5 or table_sep_count < 2:
            errors.append(
                f"00_MASTER_REPORT.md lacks structural density (found {master_h2} '##' sections, {table_sep_count} Markdown tables; expected >= 5 '##' sections and >= 2 comparison/audit tables). Add concrete technical tables or extracted prompts from 02_extracted_notes/ — NEVER count words or pad filler sentences."
            )
        if "```mermaid" not in m_txt or "|" not in m_txt:
            errors.append(
                "00_MASTER_REPORT.md must include both a Mermaid architecture diagram (```mermaid) and comparison tables (|)."
            )

        code_blocks = re.findall(r"```(?!mermaid)\w*\n(.*?)```", m_txt, flags=re.DOTALL)
        multiline_blocks = [
            b for b in code_blocks if len([ln for ln in b.strip().splitlines() if ln.strip()]) >= 4
        ]
        if len(code_blocks) < 3 or len(multiline_blocks) < 2:
            errors.append(
                f"00_MASTER_REPORT.md has {len(code_blocks)} code/prompt block(s) ({len(multiline_blocks)} multi-line >= 4 lines); expected >= 3 blocks with at least 2 substantive multi-line System Prompts/Configs (never use 1-line fake CLI commands)."
            )

        callout_count = len(
            re.findall(r"^>\s*\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", m_txt, flags=re.MULTILINE)
        )
        if callout_count < 2:
            errors.append(
                f"00_MASTER_REPORT.md has only {callout_count} GitHub callout block(s) (> [!TIP] / > [!WARNING]); expected >= 2 for visual readability."
            )

        if len(available_keyframes) >= 2:
            inline_imgs = len(re.findall(r"!\[[^\]]*\]\([^)]+\)", m_txt))
            if inline_imgs < 2:
                errors.append(
                    f"01_raw_sources/keyframes/ has {len(available_keyframes)} images, but 00_MASTER_REPORT.md embeds only {inline_imgs} inline image(s) (![caption](...)). Embed >= 2 keyframe visuals inline."
                )

        body_parts = re.split(r"^##\s+(?:10\.|[6789]\.)", m_txt, maxsplit=1, flags=re.MULTILINE)
        narrative_body = body_parts[0] if body_parts else m_txt
        inline_citations = re.findall(
            r"\[(?:#\d+|(?:yt|web|gh|rd)_[A-Za-z0-9_-]+)[^\]]*\]|\[\d{1,2}:\d{2}(?::\d{2})?\]",
            narrative_body,
        )
        if len(inline_citations) < 5:
            errors.append(
                f"Uncited narrative prose: 00_MASTER_REPORT.md contains only {len(inline_citations)} inline citation(s) ([#1], [#2, 14:20], or [MM:SS]) in narrative sections. Every technical claim must cite its source."
            )
        raw_note_mentions_in_prose = len(re.findall(r"_note\.md", narrative_body))
        if raw_note_mentions_in_prose > 5:
            errors.append(
                f"Editorial clutter violation: 00_MASTER_REPORT.md contains {raw_note_mentions_in_prose} raw '*_note.md' filename references inside narrative prose. Use compact [#1, MM:SS] citations in prose and put '*_note.md' links in the final Evidence Audit Table."
            )

        # Run Hyperresearch-grade Citation Binding, Quote & Numerical Grounding Verification
        cite_verification = audit_citations_quotes_and_numbers(m_txt, verified_sources, ws)
        if cite_verification["unresolved_citations"]:
            errors.append(
                f"Cite-Check Gate: {len(cite_verification['unresolved_citations'])} inline citation(s) do not resolve to any ingested source in sources_manifest.json: "
                + ", ".join(cite_verification["unresolved_citations"][:5])
            )
        if cite_verification["unverified_english_quotes"]:
            warnings.append(
                f"Quote-Integrity Check: {len(cite_verification['unverified_english_quotes'])} English quote(s) could not be matched verbatim in corpus: "
                + "; ".join(cite_verification["unverified_english_quotes"][:3])
            )

        slop_hits.extend(scan_file_for_slop(master_report))

    if slop_hits:
        errors.append(f"Anti-Slop scanner flagged {len(slop_hits)} forbidden phrase(s).")

    if not audit_tsv.exists() or len(audit_tsv.read_text(encoding="utf-8").splitlines()) < 2:
        warnings.append("audit_trail.tsv has no logged rows.")

    sat_metrics = compute_saturation_metrics(verified_sources, ws)
    passed = len(errors) == 0
    return {
        "passed": passed,
        "workspace": str(ws),
        "metrics": {
            "total_ingested_sources": len(sources),
            "verified_full_sources": len(verified_sources),
            "independent_sources_count": independent_count,
            "duplicate_clusters_count": ind_metrics["duplicate_clusters_count"],
            "total_raw_words_ingested": sat_metrics["total_raw_words"],
            "equivalent_book_pages": sat_metrics["equivalent_book_pages"],
            "information_saturation_pct": sat_metrics["saturation_score_pct"],
            "saturation_status": sat_metrics["status"],
            "extracted_notes_count": len(list(notes_dir.glob("*.md"))) if notes_dir.exists() else 0,
            "playbooks_count": len(playbook_files),
            "master_report_words": master_wc,
            "citation_bindings_checked": cite_verification.get("total_citation_bindings_checked", 0),
            "citation_binding_accuracy_pct": cite_verification.get("citation_binding_accuracy_pct", 100.0),
            "numerical_grounding_pct": cite_verification.get("numerical_grounding_pct", 100.0),
            "slop_violations_count": len(slop_hits),
        },
        "verification_details": {
            "syndication_clusters": ind_metrics["syndication_clusters"],
            "unresolved_citations": cite_verification.get("unresolved_citations", []),
            "unverified_english_quotes": cite_verification.get("unverified_english_quotes", []),
            "untraced_numbers_sample": cite_verification.get("untraced_numbers_sample", []),
        },
        "errors": errors,
        "warnings": warnings,
        "slop_violations": slop_hits,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a Deep Research Workspace v3.3")
    parser.add_argument("workspace", help="Path to research workspace directory")
    parser.add_argument("--min-sources", type=int, default=1, help="Minimum independent verified full sources required")
    parser.add_argument("--min-playbooks", type=int, default=1, help="Minimum modular playbooks required")
    args = parser.parse_args()

    ws = Path(args.workspace).resolve()
    report = audit_workspace(ws, min_sources=args.min_sources, min_playbooks=args.min_playbooks)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
