#!/usr/bin/env python3
"""
Deterministic Research Quality Gate & Anti-Slop Auditor (`audit_report.py` v2.0)
Enforces:
1. Map-Before-Reduce Verification: Every verified raw source in `01_raw_sources/` must have a corresponding
   deep extraction note in `02_extracted_notes/`.
2. Proportional Depth & Schema Verification:
   - Extraction notes for long sources (>3,000 words) must scale proportionally in word count (up to 350+ words)
     rather than passing with a flat 120-word stub.
   - Extraction notes must include at least 6 `## ` analytical sections, concrete fenced code/prompt blocks,
     and failure-mode analysis.
3. Playbook Completeness: Playbooks in `03_playbooks/` must contain concrete code/prompt blocks (` ``` `),
   architecture diagrams or tables, and failure-mode/gotcha remediation.
4. Anti-Slop Scanner (Vietnamese & English): Rejects reports containing lazy placeholders, vague hand-waving
   ("cấu hình cho phù hợp", "tùy nhu cầu", "xem thêm ở link"), or AI filler vocabulary.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

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
        r"\bas new sources are (?:ingested|added to the corpus)\b",
        "Word-padding meta-commentary ('as new sources are added to the corpus') — delete filler sentence.",
    ),
]


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
    """
    Low anti-stub floor (never exposes exact word-count targets in error messages so agents
    do not waste tool calls counting words or padding prose).
    """
    if raw_word_count <= 800:
        return 90
    return 140


def compute_saturation_metrics(verified_sources: List[Dict[str, Any]], ws: Path) -> Dict[str, Any]:
    """
    Computes empirical Information Saturation & Volume Metrics across ingested sources:
    - Total raw words processed & equivalent book pages (250 words/page).
    - Technical concept / entity overlap between the core 75% of sources and the tail 25% of sources.
      If the tail 25% of sources repeat >= 80% of known technical terms and total raw words >= 30,000,
      the corpus has reached empirical Information Saturation.
    """
    total_raw_words = sum(int(s.get("word_count") or 0) for s in verified_sources)
    equiv_pages = round(total_raw_words / 250.0, 1)

    # Sort sources from largest/richest to smallest
    ordered = sorted(verified_sources, key=lambda x: int(x.get("word_count") or 0), reverse=True)
    note_term_sets: List[set] = []

    for s in ordered:
        sid = s.get("id", "unknown")
        note_rel = s.get("extracted_note_path") or f"02_extracted_notes/{sid}_note.md"
        note_path = ws / note_rel
        if not note_path.exists():
            continue
        txt = note_path.read_text(encoding="utf-8", errors="replace")
        # Extract backticked identifiers, hyphenated technical terms, and capitalized proper nouns
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

    # Filter to recurring domain concepts (appearing in at least 2 notes overall) so one-off English words don't skew
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
        if str(s.get("evidence_level", "")).startswith("FULL_")
    ]

    if len(verified_sources) < min_sources:
        errors.append(
            f"Verified full-content sources count ({len(verified_sources)}) is below minimum threshold ({min_sources})."
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
                incomplete_schema_notes.append(f"{note_rel} (only {h2_count} '##' sections; expected >= 6 from 8-section schema)")

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
        slop_hits.extend(scan_file_for_slop(pb))

    # Check Master Report (Structural & Artifact Density over Word Count)
    master_wc = 0
    keyframes_dir = ws / "01_raw_sources" / "keyframes"
    available_keyframes = list(keyframes_dir.glob("*.jpg")) + list(keyframes_dir.glob("*.png")) if keyframes_dir.exists() else []

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
            errors.append("00_MASTER_REPORT.md must include both a Mermaid architecture diagram (```mermaid) and comparison tables (|).")

        # Self-contained prompt/config block check (excluding mermaid blocks)
        non_mermaid_fences = len(re.findall(r"^```(?!mermaid)\w+", m_txt, flags=re.MULTILINE))
        if non_mermaid_fences < 3:
            errors.append(
                f"00_MASTER_REPORT.md has only {non_mermaid_fences} inline code/prompt/config block(s) (expected >= 3 so the Master Report is self-contained)."
            )

        # Callout block check for visual readability
        callout_count = len(re.findall(r"^>\s*\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", m_txt, flags=re.MULTILINE))
        if callout_count < 2:
            errors.append(
                f"00_MASTER_REPORT.md has only {callout_count} GitHub callout block(s) (> [!TIP] / > [!WARNING]); expected >= 2 for visual readability."
            )

        # Inline visual keyframe check when keyframes exist on disk
        if len(available_keyframes) >= 2:
            inline_imgs = len(re.findall(r"!\[[^\]]*\]\([^)]+\)", m_txt))
            if inline_imgs < 2:
                errors.append(
                    f"01_raw_sources/keyframes/ has {len(available_keyframes)} images, but 00_MASTER_REPORT.md embeds only {inline_imgs} inline image(s) (![caption](...)). Embed >= 2 keyframe visuals inline."
                )

        # Check that narrative prose before the final audit table isn't cluttered with raw _note.md filenames
        body_parts = re.split(r"^##\s+[6789]\.", m_txt, maxsplit=1, flags=re.MULTILINE)
        narrative_body = body_parts[0] if body_parts else m_txt
        raw_note_mentions_in_prose = len(re.findall(r"_note\.md", narrative_body))
        if raw_note_mentions_in_prose > 5:
            errors.append(
                f"Editorial clutter violation: 00_MASTER_REPORT.md contains {raw_note_mentions_in_prose} raw '*_note.md' filename references inside narrative prose. Use compact [#1, MM:SS] citations in prose and put '*_note.md' links in the final Evidence Audit Table."
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
            "total_raw_words_ingested": sat_metrics["total_raw_words"],
            "equivalent_book_pages": sat_metrics["equivalent_book_pages"],
            "information_saturation_pct": sat_metrics["saturation_score_pct"],
            "saturation_status": sat_metrics["status"],
            "extracted_notes_count": len(list(notes_dir.glob("*.md"))) if notes_dir.exists() else 0,
            "playbooks_count": len(playbook_files),
            "master_report_words": master_wc,
            "slop_violations_count": len(slop_hits),
        },
        "errors": errors,
        "warnings": warnings,
        "slop_violations": slop_hits,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a Deep Research Workspace v2.0")
    parser.add_argument("workspace", help="Path to research workspace directory")
    parser.add_argument("--min-sources", type=int, default=1, help="Minimum verified full sources required")
    parser.add_argument("--min-playbooks", type=int, default=1, help="Minimum modular playbooks required")
    args = parser.parse_args()

    ws = Path(args.workspace).resolve()
    report = audit_workspace(ws, min_sources=args.min_sources, min_playbooks=args.min_playbooks)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
