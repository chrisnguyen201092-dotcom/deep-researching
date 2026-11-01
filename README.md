# `deep-researching` (v3.0) — Evidence-First Agent Skill

An evidence-first, multi-source & video-capable Deep Research operating system for AI Agents (**OpenBot**, **Grok Bot**, **Hermes Agent**, **Muse AI**, **Claude Code**, **Codex**, **Google Antigravity**, **Cursor**, **Cline**).

---

## 🤖 Instructions for AI Agents: How to Install This Skill When Given This Link

If the user asked you (an AI agent) to install this skill from a GitHub URL or local folder/zip, execute the steps matching your environment below:

### Step 1: Install Required Python Dependencies
```bash
pip install -r requirements.txt
# (Requires Python 3.10+, Node.js 18+, and optionally ffmpeg for video UI keyframe extraction)
```

### Step 2: Copy the Skill into Your Active Skill Directory

#### A. If you are an **OpenBot** Agent, **Muse AI**, **Codex**, **Grok**, **Cursor**, or **Cline**:
Install into both `.agents/skills/deep-researching` and `.claude/skills/deep-researching` inside your workspace (or globally at `~/.agents/skills/deep-researching`):
```bash
git clone https://github.com/chrisnguyen201092-dotcom/deep-researching.git /tmp/deep-researching
node /tmp/deep-researching/scripts/research_cli.mjs install ./.agents/skills/deep-researching
node /tmp/deep-researching/scripts/research_cli.mjs install ./.claude/skills/deep-researching
```
*(Or via the standard Agent Skills CLI: `npx skills add chrisnguyen201092-dotcom/deep-researching`)*

#### B. If you are **Hermes Agent** (`~/.hermes`):
```bash
git clone https://github.com/chrisnguyen201092-dotcom/deep-researching.git ~/.hermes/skills/deep-researching
pip install -r ~/.hermes/skills/deep-researching/requirements.txt
```

#### C. If you are **Claude Code** (Standalone):
```bash
git clone https://github.com/chrisnguyen201092-dotcom/deep-researching.git ~/.claude/skills/deep-researching
pip install -r ~/.claude/skills/deep-researching/requirements.txt
```

### Step 3: Verify Toolchain Readiness
```bash
node ./.agents/skills/deep-researching/scripts/research_cli.mjs doctor
```

---

## 🚀 Core Capabilities (v3.0)

1. **Multi-Bucket Autonomous Discovery (`research_cli.mjs discover`):**
   - Queries **YouTube (`ytsearch`)**, **GitHub Repositories & Issues API**, **Hacker News Algolia API**, and **Reddit Search JSON** in parallel without relying on the LLM's built-in search tool.
2. **4-Tier YouTube Deep Ingestion (`research_cli.mjs yt`):**
   - Tier 1 Disk Cache $\rightarrow$ Tier 2 `youtube-transcript-api` $\rightarrow$ Tier 3 `yt-dlp` JSON3/VTT captions $\rightarrow$ Tier 4 **Whisper ASR Fallback** (`GROQ_API_KEY` / `OPENAI_API_KEY` / local `faster-whisper`) for zero-caption videos.
   - **Hybrid Visual Keyframe Prober (`--keyframes`):** Combines spoken visual cues (`"on my screen"`, `"this prompt"`), creator chapter transitions, and periodic silent-slide entropy probes via `ffmpeg` (`T+2s`, `T+5s`) to capture high-density UI & slide screenshots.
   - **Affiliate Filter & Auto-Snowball (`--auto-snowball`):** Filters out sponsor/affiliate noise and automatically ingests primary documentation links.
3. **Specialized Web & Community Extractors (`research_cli.mjs web`):**
   - Native API extractors for **GitHub Repos & `/blob/` files**, **GitHub Issues + 30 Comments**, **X/Twitter Posts & Longform Articles** (via `api.fxtwitter.com`), **Reddit Threads + Top 25 Comments**, and **Hacker News Stories + Top 25 Comments**, plus `lxml` Markdown and `r.jina.ai` fallback.
4. **Deterministic Anti-Slop & Information Saturation Auditor (`research_cli.mjs audit`):**
   - Enforces 1-to-1 Map-Before-Reduce extraction notes (`02_extracted_notes/`), proportional depth scaling, Diátaxis playbooks (`03_playbooks/`), inline visual embeds, and calculates empirical **Information Saturation (`information_saturation_pct`)** and **Total Raw Word Volume**.

---

## 📂 Package Structure

```text
deep-researching/
├── SKILL.md                              # Agent Skills specification entrypoint
├── README.md                             # Self-installation guide for AI agents & humans
├── requirements.txt                      # Python dependencies
├── scripts/
│   ├── research_cli.mjs                  # Cross-platform Node.js CLI dispatcher
│   ├── discover_sources.py               # 4-Bucket autonomous source discovery engine
│   ├── yt_ingest.py                      # 4-Tier YouTube transcript + Smart FFmpeg keyframe extractor
│   ├── web_ingest.py                     # GitHub / X / Reddit / HN / Web Markdown extractor
│   └── audit_report.py                   # Deterministic Anti-Slop & Saturation Gate
└── resources/
    ├── extraction_schema.md              # 8-Dimension 1-to-1 source extraction schema
    ├── diataxis_playbook_guide.md        # 5 Laws of Critical Depth, ROI Tiering & Presentation
    └── audit_trail_template.tsv          # Provenance audit log template
```
