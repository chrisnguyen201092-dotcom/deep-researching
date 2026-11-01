# Source Extraction Schema (Phase 4 — Map Step)

For **every** verified source in `01_raw_sources/`, create a dedicated file `02_extracted_notes/<source_id>_note.md` using the structure below. Do NOT summarize multiple sources into one note.

---

```markdown
# Extraction Note: [Source Title]

- **Source ID:** `<source_id>`
- **Origin URL:** [URL]
- **Author / Creator & Date:** [Author, YYYY-MM-DD]
- **Evidence Level:** `FULL_TRANSCRIPT_VERIFIED` | `FULL_TRANSCRIPT_PLUS_KEYFRAMES` | `FULL_CONTENT_VERIFIED` | `METADATA_ONLY_NO_SUBS`

## 1. Architecture & Core Mechanism
- How many components/agents/modules are involved, what is each component's exact role, and how does data or control flow between them?

## 2. Exact Setup & Configuration
- What exact CLI commands, installation steps, environment variables, permissions, models, or UI toggles are used?

## 3. Step-by-Step Live Demo / Walkthrough (With Timestamps if Video)
- Trace each concrete operation demonstrated (`[MM:SS] Step 1 -> Input -> Action -> Output`).

## 4. Verbatim Prompts, Schemas, or Code Snippets
- Copy the exact prompts, YAML/JSON configs, or code blocks shown or spoken in the source.
```text
[Exact prompt or config]
```

## 5. Automation & Scaling Pattern
- How does the creator turn a manual one-off action into a reusable skill, cron job, or multi-agent routine?

## 6. Proven Results vs. Unverified Marketing Claims (Epistemic Tiering)
Tag each major claim with one of the 5 Epistemic Tiers:
- **`[Direct]`**: Explicitly proven in the demo or source code (`file:line` or `[MM:SS]`).
- **`[Supported]`**: Converging evidence across multiple independent sources.
- **`[Inferred]`**: Logical deduction not explicitly stated by the author.
- **`[Speculative]`**: Claimed by the author (e.g., "saves 90% time") with no live proof.
- **`[Unknown]`**: Could not be verified (state what was checked).

## 7. Failure Modes, Pitfalls & Limits Surfaced
- Where did the tool/workflow break, hit rate/billing limits, hallucinate, or require human intervention?

## 8. Hard Technical Quotas, Numerical Specs, Pricing & Version Dates
- Extract EVERY concrete number mentioned: max routines/agents, minimum intervals (e.g. `5 min`), file/video size caps (e.g. `25 MB` / `250 MB`), approval timeout minutes (`10 min` / `30 min`), context compaction thresholds (`30-50 messages`), subscription tier prices (`$30` / `$100` / `$200`), and exact changelog/release dates.

## 9. Cross-Source Contradictions & Discrepancies
- Note any claim in this source that conflicts with official docs or other sources (e.g., creator says "1 VM per bot" whereas official security docs state "1 shared VM per account with separate virtual displays"; or outdated pricing from an older build).

## 10. Snowball Leads (High-Value Referenced Sources)
- Which specific official doc subpages (`/security`, `/faq`, `/use-cases`), repos, papers, or creator workflows mentioned in this source should be fetched next?
```
