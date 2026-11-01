# Diátaxis, Critical Depth & Editorial Standard (Phase 5 — Reduce Step)

## 1. The Anti-Slop Golden Rule (Project-Swap Test)

> **Rule 27 (Project-Swap Test):** If you can replace the name of the subject in a sentence with another tool's name (e.g., replacing "Grok Bot" with "Zapier") and the sentence still sounds true, **DELETE THE SENTENCE**.
> - **Bad (Slop):** *"Grok Bot helps automate complex workflows and saves significant time for teams."*
> - **Good (Concrete):** *"Grok Bot shares one cloud VM across all personal bots, caps Auto-Review at 20 Allow rules and 20 Ask rules (1,000 chars each), and disables any routine after 10 consecutive failures."*

### Forbidden Slop Patterns (Enforced by `audit_report.py`)
- Never write `"cấu hình cho phù hợp"`, `"tùy theo nhu cầu của bạn"`, `"bạn có thể tự tìm hiểu thêm"`, or `"xem chi tiết tại video"`.
- Never use placeholders (`[TODO]`, `TBD`, `FIXME`).
- When a fact is unknown (`[Unknown]`), state explicitly what you searched: *"Searched official docs, GitHub issues, and 8 tutorial transcripts for keyword X; no evidence found."*

---

## 2. Five Laws of Critical Depth, Usefulness & Presentation

A best-in-market research report must read like an authoritative, opinionated **Definitive Guide**, never like a dry technical inventory or a fragmented listicle.

### Law 1: Critical ROI Tiering (Never Output a Flat Listicle of Use Cases)
Creators and conference speakers present every demo as "revolutionary." You MUST critically evaluate and classify discovered workflows into **3 Explicit Value Tiers**:
1. **Tier 1 — Core OS / Daily Must-Build (ROI 9.5/10):** The 20% of workflows that deliver 80% of daily value with minimal token burn and low fragility.
2. **Tier 2 — Domain Specialist Weapons + Indie/Local Stack Replacements (ROI 8.5–9.0/10):** Deep engineering, GTM, or data pipelines. **Mandatory Rule:** Whenever a source relies on expensive enterprise SaaS (e.g., `Salesforce`, `Hex`, `Sumble`, `Navan`), provide a concrete **Free / Local / Indie Stack Replacement** box (`> [!TIP]`) showing how an individual builder can achieve the exact same outcome using local files, SQLite, Google Sheets, or open-source MCP servers.
3. **Tier 3 — "Stage Demos" & Low-ROI / Over-Engineered Workflows (Critical Pushback):** Explicitly critique workflows that look impressive on stage (e.g., one-off apartment hunting or enterprise procurement bots) but have poor ROI, high maintenance overhead, or security/CAPTCHA fragility for individuals.

### Law 2: The Self-Contained "Canonical Blueprint" & Day-1 Roadmap
- Do not leave the reader confused by 10 different naming schemes from 10 creators. Synthesize all sources into **1 Unified Canonical Architecture** (e.g., *"The Golden 5-Agent Roster"*).
- **Make `00_MASTER_REPORT.md` Self-Contained:** Include the core copy-pasteable System Prompts, Skill templates, and configuration blocks **directly inside `00_MASTER_REPORT.md`** (`>= 3` fenced code/prompt blocks) so the user can build the core system without jumping across 5 files.
- Always include a **Phased Implementation Roadmap**: **Phase 1 (First 30 Minutes)** $\rightarrow$ **Phase 2 (Days 2–3)** $\rightarrow$ **Phase 3 (Week 2)**.

### Law 3: 1-to-1 Cross-Platform Feature Translation
When comparing commercial cloud tools against local-first or open-source alternatives, include a **1-to-1 Feature Translation Matrix** showing exactly how each commercial feature maps to local directories, CLI flags, or free equivalents.

### Law 4: Clean Citations & Visual Breathing Room (No Raw Filename Clutter in Prose)
- **Clean Prose Citations:** Never clutter narrative sentences with raw filename links like `([yt_j0Pqe8c07vY_note.md](...) [15:45])`. Use compact numbered references in prose (e.g., `[#1, 14:20]`, `[#4, 09:13]`) and map `[#1]..[#N]` to their clickable `_note.md` and raw source links in the final **Evidence Audit Table** at the bottom of `00_MASTER_REPORT.md`.
- **Callout Blocks & Typography:** Use GitHub-style alert callouts (`> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!WARNING]`, `> [!CAUTION]`) to break up long sections and highlight critical gotchas. Avoid bolding more than 2–3 short phrases per paragraph.

### Law 5: Mandatory Inline Visual Evidence (`![caption](...)`)
- Whenever `01_raw_sources/keyframes/` contains extracted UI screenshots or presentation slides, you MUST embed the most informative keyframes directly inline (`![Detailed descriptive caption](file:///.../01_raw_sources/keyframes/...)`) inside both `00_MASTER_REPORT.md` and `03_playbooks/*.md`.

---

## 3. Deliverable Structure

### A. `00_MASTER_REPORT.md` (The Self-Contained Definitive Guide)
1. **Executive Disambiguation & Decision Matrix**: Clear breakdown of competing/similarly named projects + comparison table.
2. **Internal Architecture (`mermaid`) & 1-to-1 Feature Translation Matrix**: Under-the-hood mechanics + how to map cloud features to local/free setups.
3. **Critically Ranked Use-Case Analysis (Tier 1 Core $\rightarrow$ Tier 2 Specialist + Indie Replacements $\rightarrow$ Tier 3 Stage Demo Critique)**: Deep analysis with embedded keyframe screenshots (`![...](...)`).
4. **The Canonical Blueprint ("Golden Setup")**: Unified architecture diagram + model routing table + **inline copy-pasteable System Prompts & Configs**.
5. **Real-World Failure Modes, Cost & Security Traps (Gotchas)**: Callout boxes + rapid-reference remediation table.
6. **Phased Implementation Roadmap**: First 30 Minutes $\rightarrow$ Day 3 $\rightarrow$ Week 2.
7. **Playbook Index & Numbered Evidence Audit Table (`[#1]` to `[#N]`)**: Links to `03_playbooks/*.md`, `02_extracted_notes/*_note.md`, and `01_raw_sources/*.md`.

### B. `03_playbooks/playbook-<NN>-<slug>.md` (Diátaxis: Deep How-To Playbooks)
Each major domain workflow gets its own standalone file in `03_playbooks/` containing:
1. **Objective & When to Use**
2. **Architecture & Data Flow (`mermaid`)**
3. **Prerequisites & Setup**
4. **Step-by-Step Execution (A–Z) with Verbatim Prompts/Code & Inline Keyframe Screenshots (`![...](...)`)**
5. **Worked Input → Output Example**
6. **Failure Modes, Gotchas & Verified Fixes Table**
