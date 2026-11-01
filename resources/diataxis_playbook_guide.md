# Diátaxis, Critical Depth & Editorial Standard (Phase 5 — Reduce Step)

## 1. The Anti-Slop Golden Rule (Project-Swap Test)

> **Rule 27 (Project-Swap Test):** If you can replace the name of the subject in a sentence with another tool's name (e.g., replacing "Grok Bot" with "Zapier") and the sentence still sounds true, **DELETE THE SENTENCE**.
> - **Bad (Slop):** *"Grok Bot helps automate complex workflows and saves significant time for teams."*
> - **Good (Concrete):** *"Grok Bot shares one cloud VM across all personal bots, caps Auto-Review at 20 Allow rules and 20 Ask rules (1,000 chars each), and disables any routine after 10 consecutive failures."*

### Forbidden Slop Patterns (Enforced by `audit_report.py`)
- Never write `"cấu hình cho phù hợp"`, `"tùy theo nhu cầu của bạn"`, `"bạn có thể tự tìm hiểu thêm"`, or `"xem chi tiết tại video"`.
- Never use placeholders (`[TODO]`, `TBD`, `FIXME`).
- **Zero Word-Counting & No Meta-Commentary Padding:** Never count words (`wc`) or append filler sentences about the research process itself (e.g., *"The report will be refreshed as new sources are added to the corpus"*, *"as more transcripts become available"*). `audit_report.py` grades structural artifact density (tables, `## ` sections, `mermaid` diagrams, and fenced code/prompt blocks), never word count.
- When a fact is unknown (`[Unknown]`), state explicitly what you searched: *"Searched official docs, GitHub issues, and 8 tutorial transcripts for keyword X; no evidence found."*

---

## 2. Seven Laws of Critical Depth, Usefulness & Presentation

A best-in-market research report must read like an authoritative, opinionated **Definitive Operating Manual**, never like a dry technical inventory or a compressed summary.

### Law 1: Critical ROI Tiering & Multi-Profession Depth (Never Output a Shallow Listicle)
Creators and conference speakers present every demo as "revolutionary." You MUST critically evaluate and classify discovered workflows into **3 Explicit Value Tiers** AND break down how the tool is used across **8–10 distinct job functions/professions** (e.g., Chief of Staff/Admin, Sales/CRM, Customer Support, Competitor/Price Research, Content/Marketing, Software Engineering, Data/ML, Finance/Procurement, Personal/Family, Enterprise):
1. **Tier 1 — Core OS / Daily Must-Build (ROI 9.5/10):** The 20% of workflows that deliver 80% of daily value with minimal token burn and low fragility.
2. **Tier 2 — Domain Specialist Weapons + Indie/Local Stack Replacements (ROI 8.5–9.0/10):** Deep engineering, GTM, or data pipelines. **Mandatory Rule:** Whenever a source relies on expensive enterprise SaaS (e.g., `Salesforce`, `Hex`, `Sumble`, `Navan`), provide a concrete **Free / Local / Indie Stack Replacement** box (`> [!TIP]`) showing how an individual builder can achieve the exact same outcome using local files, SQLite, Google Sheets, or open-source MCP servers.
3. **Tier 3 — "Stage Demos" & Low-ROI / Over-Engineered Workflows (Critical Pushback):** Explicitly critique workflows that look impressive on stage (e.g., one-off apartment hunting or enterprise procurement bots) but have poor ROI, high maintenance overhead, or security/CAPTCHA fragility for individuals.
- For each profession/domain, state clearly: **Bot làm gì (What it does), Cần gì (Prerequisites), Nhịp chạy (Cadence), Đầu ra (Output), và Không nên giao (What NOT to delegate)**, backed by real numbers from the corpus.

### Law 2: The Self-Contained "Canonical Blueprint" & Step 0 → Step 10 Zero-to-One Onboarding
- Walk the reader through **Step 0 to Step 10 from Zero to First Real Production Task** (choosing the entry tier, installing, logging in, naming the first bot, the 5-part task delegation formula, connecting the first tool, running a narrow real task, turning it into a Skill, scheduling a Routine, adding a second bot, and weekly usage audits — plus step-by-step traps).
- Synthesize all creator setups into **1 Unified Canonical Architecture** with **inline copy-pasteable System Prompts, Skill templates, and configuration blocks** (`>= 3` multi-line fenced blocks) directly inside `00_MASTER_REPORT.md`.

### Law 3: 1-to-1 Cross-Platform Feature Translation & Disambiguation
- Disambiguate all similarly named products/repos/tiers upfront in a crisp table (e.g., `Grok` vs. `Grok Build` vs. `Grok Bot` vs. `OpenBot (CopilotKit)` vs. `OpenBot (nightly-labs)` vs. `OpenBot (Intel)`).
- Include a **1-to-1 Feature Translation Matrix** showing how commercial cloud features map to self-hosted or local-first equivalents.

### Law 4: Clean Citations & Visual Breathing Room (No Raw Filename Clutter in Prose)
- **Clean Prose Citations:** Never clutter narrative sentences with raw filename links like `([yt_j0Pqe8c07vY_note.md](...) [15:45])`. Use compact numbered references in prose (e.g., `[#1, 14:20]`, `[#4, 09:13]`) and map `[#1]..[#N]` to their clickable `_note.md` and raw source links in the final **Evidence Audit Table**.
- **Callout Blocks & Typography:** Use GitHub-style alert callouts (`> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!WARNING]`, `> [!CAUTION]`) to highlight critical gotchas.

### Law 5: Mandatory Inline Visual Evidence (`![caption](...)`)
- Whenever `01_raw_sources/keyframes/` contains extracted UI screenshots or presentation slides, you MUST embed the most informative keyframes directly inline (`![Detailed descriptive caption](file:///.../01_raw_sources/keyframes/...)`) inside both `00_MASTER_REPORT.md` and `03_playbooks/*.md`.

### Law 6: Hard Quotas Table, Version/Pricing Timeline & Cross-Source Contradiction Resolution
- **Hard Technical Quotas & Limits Table:** Always extract and tabulate exact system numbers (e.g., max routines per bot `50`, run history `20`, min interval `5 mins`, bots per group `2–6`, file/video size caps `25 MB` / `250 MB`, approval expiry `10–30 mins`, auto-compaction threshold `30–50 messages`).
- **Chronological Version & Pricing Timeline Table:** Trace when pricing/quotas changed (e.g., Beta launch → plan expansion → unified subscription pool) so readers understand why older videos quote different prices (`$20`, `$100`, `$200`).
- **Mandatory Conflict Resolution Section ("Những chỗ mâu thuẫn / chưa chắc & cách xử lý"):** Explicitly list 5–10 contradictions between videos, changelogs, and official docs, and explain how you resolved each one (official docs and newer changelogs trump older creator claims).

### Law 7: Pure Native Editorial Voice (No Lazy Code-Switching or Summary Compression)
- When writing in Vietnamese, write 100% natural, crystal-clear, idiomatic Vietnamese (translate/adapt prompt templates and workflow instructions into natural Vietnamese; keep only CLI commands, paths, and code identifiers in English).
- Never compress `00_MASTER_REPORT.md` into a short 1,200-word executive overview when publishing to HTML or Markdown; preserve the full depth of all sections.

---

## 3. Deliverable Structure

### A. `00_MASTER_REPORT.md` (The 11-Section Self-Contained Definitive Guide)
0. **Kết luận trước (BLUF — Bottom Line Up Front)**: Plain-language definition of what the product actually is, **3 Proven Strengths**, **3 Proven Weaknesses**, **Nên dùng khi (Use When)** vs. **Không nên dùng khi (Do Not Use When)**.
1. **Làm rõ tên gọi & Ma trận phân biệt (Executive Disambiguation Matrix)**: Clear table separating all similarly named products/repos/tiers.
2. **Cơ chế lõi, Kiến trúc (`mermaid`), Bảo mật & Bảng Giới hạn Kỹ thuật Cứng (Hard Quotas & Specs Table)**: Under-the-hood VM/container/memory mechanics, approval/Auto-Review/Vault model, and a mandatory **Hard Technical Limits Table**.
3. **Quy trình từ Số 0 đến Việc thật đầu tiên (Bước 0 → Bước 10 + Cạm bẫy từng bước)**: Concrete end-to-end onboarding sequence + step-by-step pitfalls.
4. **Cách dùng tốt nhất từ người dùng thật: 9 Nguyên tắc, 4 Mẫu câu lệnh (Prompts) & Cách giữ Usage**: Recurring operational principles, copy-pasteable multi-line prompt templates, and token/cost conservation tactics.
5. **Phân tích & Xếp hạng Use Case theo ROI và theo Nghề / Bộ phận (Tier 1 → Tier 2 + Indie Stack Replacements → Tier 3 Stage Demos across 8–10 Professions)**: Deep breakdown across 8–10 job functions with quantitative proofs + embedded keyframe screenshots (`![...](...)`).
6. **Chỗ hỏng thực tế & Hỏng như thế nào (Chi phí, Độ tin cậy, Bảo mật, Khoá/Sở hữu & Việc tuyệt đối không giao)**.
7. **Giá, Hạn mức & Dòng thời gian Thay đổi (Chronological Version Timeline + Current Pricing Table + Real User Spend Reports)**.
8. **Giải pháp thay thế & Ma trận Chuyển đổi 1-đối-1 (Head-to-Head Comparison of OpenBot CopilotKit vs. OpenBot nightly-labs vs. Claude Code/Cowork vs. Codex vs. Hermes Agent vs. OpenClaw + 1-to-1 Feature Translation Matrix)**.
9. **Kế hoạch triển khai 30 ngày (Tuần 1 → Tuần 4 + 7 Routine đáng thử đầu tiên)**.
10. **Những chỗ mâu thuẫn / chưa chắc & Bảng Kiểm toán Bằng chứng (`[#1]` to `[#N]`)**: Explicit resolution of 5–10 contradictions across sources + numbered Evidence Audit Table linking to `03_playbooks/*.md`, `02_extracted_notes/*_note.md`, and `01_raw_sources/*.md`.

### B. `03_playbooks/playbook-<NN>-<slug>.md` (Diátaxis: Deep How-To Playbooks)
Each major domain workflow gets its own standalone file in `03_playbooks/` containing:
1. **Objective & When to Use**
2. **Architecture & Data Flow (`mermaid`)**
3. **Prerequisites & Setup**
4. **Step-by-Step Execution (A–Z) with Verbatim Prompts/Code & Inline Keyframe Screenshots (`![...](...)`)**
5. **Worked Input → Output Example**
6. **Failure Modes, Gotchas & Verified Fixes Table**
