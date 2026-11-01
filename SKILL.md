---
name: deep-researching
description: "Deep research & video/web extraction skill (nghiên cứu sâu tất cả video YouTube, GitHub, docs, Reddit/HN). Extracts full transcripts, UI keyframes, 1-to-1 notes, and Diataxis playbooks with anti-slop auditing."
example-prompt: "Use the deep-researching skill to research all videos, GitHub repos, and guides on [Topic], extract best workflows and use cases, and synthesize a full Master Report and Playbooks."
---

# Deep Researching (Evidence-First Operating System)

## When to use this skill
- User asks for "deep research", "research toàn diện", "research hết video/tài liệu", or an "operating manual / playbook".
- User wants actionable workflows, configurations, and verbatim prompts extracted from YouTube tutorials, official documentation, GitHub repositories, and community discussions.
- User complains that standard AI research is too shallow, summarized, or only returns links/metadata.

---

## Core Execution Checklist

Copy this checklist to track progress. Never skip straight from searching to writing the final report.

- [ ] **Phase 1: Scope & STORM 3-Perspective Plan** — Run `research_cli.mjs doctor` and `research_cli.mjs init <workspace_dir> --topic "<Topic>"`. Fill out `00_research_plan.md`.
- [ ] **Phase 2: 4-Bucket Discovery & Snowballing** — Search across Primary Docs/GitHub, Hands-on YouTube Demos, Expert Deep-Dives, and Community Failure Modes.
- [ ] **Phase 3: Physical Source Ingestion** — Run `research_cli.mjs yt` on target videos and `research_cli.mjs web` on target web/GitHub URLs to populate `01_raw_sources/`.
- [ ] **Phase 4: 1-to-1 Deep Extraction (Map Step)** — Read every verified file in `01_raw_sources/` (and inspect extracted keyframes if needed) and write a dedicated note in `02_extracted_notes/<source_id>_note.md` following [extraction_schema.md](resources/extraction_schema.md).
- [ ] **Phase 5: Diátaxis Synthesis (Reduce Step)** — Write modular playbooks in `03_playbooks/playbook-*.md` and the unified `00_MASTER_REPORT.md` following [diataxis_playbook_guide.md](resources/diataxis_playbook_guide.md).
- [ ] **Phase 6: Deterministic Code Audit** — Run `research_cli.mjs audit <workspace_dir>` and fix any flagged errors or slop violations until it exits with code `0` (`"passed": true`).

---

## Step-by-Step Instructions

### Phase 1: Initialize Workspace & STORM Perspectives
1. Verify the local extraction toolchain (`python`, `yt-dlp`, `youtube_transcript_api`, `ffmpeg`):
   ```bash
   node "<skill_dir>/scripts/research_cli.mjs" doctor
   ```
2. Initialize a dedicated research workspace folder in the current project (e.g., `./research-<slug>`):
   ```bash
   node "<skill_dir>/scripts/research_cli.mjs" init "./research-<slug>" --topic "<Topic Name>"
   ```
3. Edit `00_research_plan.md` to formulate sub-questions from three distinct perspectives (**STORM pattern**):
   - **Implementer:** Exact setup, UI clicks, CLI flags, verbatim prompts, skill/routine automation steps.
   - **Skeptic / Debugger:** Marketing vs. reality, rate limits, billing traps, security risks, failure cases.
   - **Systems Architect:** Internal mechanisms, state/memory model, sandboxing, comparison against alternatives.

### Phase 2: 4-Bucket Autonomous Discovery & Adaptive Saturation Quota
1. **Run the Multi-Bucket Autonomous Discovery Engine (`discover`):**
   ```bash
   node "<skill_dir>/scripts/research_cli.mjs" discover "<Primary Topic>" --queries "<Query Variant 1>" "<Query Variant 2>" --out "./research-<slug>"
   ```
   - `discover_sources.py` v3.0 queries **all 4 Mandatory Buckets in parallel** without depending on the LLM's built-in search tool:
     - **Bucket 1 (Primary/Official):** GitHub Repositories API + GitHub Issues/PRs API.
     - **Bucket 2 (Hands-on Video Demos):** Multi-angle YouTube search (`ytsearch`), filtering out Shorts (`<180s`) and ranking by duration + tutorial density.
     - **Bucket 3 (Expert Deep-Dives):** Hacker News Algolia Story API + external technical blogs.
     - **Bucket 4 (Community & Failure Modes):** Reddit JSON Search API + HN discussion threads + GitHub bug issues.
   - Outputs ranked candidates to `00_discovered_candidates.md` and `00_discovered_candidates.json` (pass `--auto-ingest` to immediately ingest the top YouTube and Web candidates).
2. **Adaptive Source Quota & Information Saturation Rule (How many sources is enough?):**
   - Never rely on an arbitrary source count alone; evaluate **Total Raw Word Volume** + **Information Saturation (`information_saturation_pct` in `audit_report.py`)**:
     - **Tier A — Focused Tool / New Release Deep-Dive:** `12–15` full-length sources (`>= 35,000` raw words, ~140+ book pages) across all 4 Buckets, reaching `>= 80%` Information Saturation.
     - **Tier B — Broad Architecture / Multi-Tool Comparison:** `25–40` sources (`>= 75,000` raw words) so every competing framework and community failure mode is represented.
   - Inspect `Outbound Links (Snowballing Candidates)` in `01_raw_sources/*.md` and continue snowballing until `audit_report.py` reports `saturation_status: "SATURATED_HIGH_CONFIDENCE"`.

### Phase 3: Physical Source Ingestion (Never Confuse Discovery with Reading)
Do NOT rely on search snippets or YouTube titles/descriptions. Ingest full content onto disk first:

1. **Ingest YouTube Videos (4-Tier Transcript/ASR + Hybrid Chapter/Cue Keyframes + Auto-Snowball):**
   ```bash
   node "<skill_dir>/scripts/research_cli.mjs" yt "<video_url_1>" "<video_url_2>" --out "./research-<slug>" --keyframes --max-keyframes 4 --auto-snowball --workers 3
   ```
   - `yt_ingest.py` v3.0 uses a **4-tier pipeline**: `disk_cache` -> `youtube-transcript-api` -> `yt-dlp` JSON3 captions -> **Tier 3 Whisper ASR Fallback** (auto-downloads lightweight low-bitrate audio and transcribes via Groq/OpenAI Whisper API or local `faster-whisper` when captions are disabled) -> explicit `METADATA_ONLY_NO_SUBS` tag.
   - **Hybrid Visual Keyframe Selector (`--keyframes`):** Combines spoken visual cues (`"on my screen"`, `"this prompt"`) with **creator chapter transitions (`start_time + 8s`)** and **periodic silent-slide entropy probes** (catching silent slide changes even when the speaker doesn't verbally announce them), probing `(T + 2s)` and `(T + 5s)` via `ffmpeg` to keep the highest-entropy UI/slide frame.
   - **Affiliate Filter & Auto-Snowball (`--auto-snowball`):** Separates primary documentation/GitHub links from affiliate/sponsor noise and auto-ingests top primary doc URLs.

2. **Ingest Web Articles, GitHub Repos/Issues, X/Twitter Posts, Reddit & Hacker News Threads:**
   ```bash
   node "<skill_dir>/scripts/research_cli.mjs" web "<url_1>" "<url_2>" --out "./research-<slug>" --workers 4
   ```
   - `web_ingest.py` v3.0 includes native API extractors for **GitHub Repos & `/blob/` files**, **GitHub Issues & PR comments**, **X/Twitter Statuses & Longform Articles** (via `api.fxtwitter.com` bridge), **Reddit Threads + Top 25 Comments** (`.json` API), and **Hacker News Discussions + Top 25 Technical Comments** (Algolia Item API), plus `lxml` structured Markdown and `r.jina.ai` fallback.
   - If a source is behind a strict login/paywall or blocked, use the interactive browser tool if available, or record it honestly under the `[Unknown]` epistemic tier.

### Phase 4: 1-to-1 Deep Extraction (Map Step — Extraction Before Synthesis)
1. Read [resources/extraction_schema.md](resources/extraction_schema.md).
2. For **every** verified source in `01_raw_sources/sources_manifest.json` (`FULL_TRANSCRIPT_VERIFIED`, `FULL_TRANSCRIPT_PLUS_KEYFRAMES`, or `FULL_CONTENT_VERIFIED`), read the raw file in `01_raw_sources/` completely and write its corresponding extraction note at `02_extracted_notes/<source_id>_note.md`.
3. Every extraction note MUST capture all 8 dimensions:
   - Architecture & mechanism
   - Exact setup & configuration
   - Step-by-step live demo walkthrough (with `[MM:SS]` timestamps)
   - Verbatim prompts / code / config blocks
   - Automation & scaling pattern
   - Proven results vs. speculative claims (`[Direct]`, `[Supported]`, `[Inferred]`, `[Speculative]`, `[Unknown]`)
   - Failure modes & limits
   - Snowball leads

### Phase 5: Diátaxis Synthesis (Reduce Step — Topic-Driven, Never Source-by-Source)
1. Read [resources/diataxis_playbook_guide.md](resources/diataxis_playbook_guide.md).
2. **Write Modular Playbooks First (`03_playbooks/playbook-01-*.md`, `playbook-02-*.md`, ...):**
   - Group knowledge by **Use Case / Workflow**, synthesizing the best practices from multiple creators/docs into one definitive guide per workflow.
   - Writing each playbook as a separate file prevents output-token truncation and guarantees A-to-Z depth (Mechanism, Exact Setup, Verbatim Prompt/Config block, Input->Output example, and Failure Recovery).
3. **Write the Master Operating Manual (`00_MASTER_REPORT.md`):**
   - Make `00_MASTER_REPORT.md` a **self-contained, critically deep Definitive Guide** following the **5 Laws in [diataxis_playbook_guide.md](resources/diataxis_playbook_guide.md)**:
     1. **Executive Disambiguation & 1-to-1 Feature Translation Matrix** (mapping commercial/cloud features to local/free equivalents).
     2. **Critical ROI Tiering of Use Cases:** Classify workflows into **Tier 1 (Core Daily Must-Build)**, **Tier 2 (Specialist Weapons + Free/Indie Stack Replacements for Enterprise Tools)**, and **Tier 3 (Stage Demos / Low-ROI Critique)**.
     3. **The Canonical Blueprint ("Golden Setup"):** Synthesize fragmented creator setups into 1 unified architecture with **inline copy-pasteable System Prompts/Configs** (`>= 3` fenced blocks) and a **First 30 Minutes $\rightarrow$ Day 3 $\rightarrow$ Week 2 Roadmap**.
     4. **Clean Editorial Readability & Inline Visuals:** Use compact `[#1, 14:20]` citations in prose (keeping `_note.md` links in the bottom Evidence Table), include GitHub alert callouts (`> [!TIP]`, `> [!WARNING]`), and embed extracted keyframe screenshots (`![caption](file:///.../keyframes/...)`) inline.
   - Apply **Unslop Rule 27 (Project-Swap Test)**: Cut any generic sentence that would still sound true if you swapped the subject's name with another tool.

### Phase 6: Deterministic Quality Gate (`audit_report.py`)
Before presenting the final response to the user, run the automated auditor:
```bash
node "<skill_dir>/scripts/research_cli.mjs" audit "./research-<slug>" --min-sources 3 --min-playbooks 2
```
- If `"passed": false`, inspect the `errors` and `slop_violations` arrays in the JSON output, fix every missing extraction note, short playbook, or forbidden vague phrase, and re-run `audit` until `"passed": true`.

---

## Resources
- [CLI Dispatcher (`scripts/research_cli.mjs`)](scripts/research_cli.mjs)
- [YouTube Multi-Tier Extractor (`scripts/yt_ingest.py`)](scripts/yt_ingest.py)
- [Web & GitHub Extractor (`scripts/web_ingest.py`)](scripts/web_ingest.py)
- [Deterministic Report Auditor (`scripts/audit_report.py`)](scripts/audit_report.py)
- [8-Dimension Source Extraction Schema (`resources/extraction_schema.md`)](resources/extraction_schema.md)
- [Diátaxis & Anti-Slop Editorial Guide (`resources/diataxis_playbook_guide.md`)](resources/diataxis_playbook_guide.md)
- [Audit Trail Template (`resources/audit_trail_template.tsv`)](resources/audit_trail_template.tsv)
