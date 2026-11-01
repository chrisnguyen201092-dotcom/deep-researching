#!/usr/bin/env node
/**
 * Unified CLI Dispatcher for the `deep-researching` Skill.
 * Automatically resolves Python 3, yt-dlp, youtube-transcript-api, and ffmpeg paths on Windows/macOS/Linux
 * even when they are not in the default shell PATH.
 */

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, writeFileSync, copyFileSync, cpSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import os from "node:os";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const SKILL_ROOT = resolve(__dirname, "..");

function findExecutable(name, candidatePaths = []) {
  const isWin = process.platform === "win32";
  const ext = isWin && !name.endsWith(".exe") ? `${name}.exe` : name;

  // 1. Check candidate paths first
  for (const candidate of candidatePaths) {
    if (candidate && existsSync(candidate)) {
      return candidate;
    }
  }

  // 2. Check system PATH using where/which
  const probe = spawnSync(isWin ? "where.exe" : "which", [name], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });
  if (probe.status === 0 && probe.stdout) {
    const firstLine = probe.stdout.split(/\r?\n/).find((l) => l.trim().length > 0);
    if (firstLine && existsSync(firstLine.trim())) {
      return firstLine.trim();
    }
  }

  return null;
}

function findWinGetFfmpeg() {
  if (process.platform !== "win32") return null;
  const localAppData = process.env.LOCALAPPDATA || join(os.homedir(), "AppData", "Local");
  const wingetPkgDir = join(localAppData, "Microsoft", "WinGet", "Packages");
  if (!existsSync(wingetPkgDir)) return null;

  try {
    const entries = readdirSync(wingetPkgDir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory() && entry.name.toLowerCase().includes("ffmpeg")) {
        const pkgPath = join(wingetPkgDir, entry.name);
        const subDirs = readdirSync(pkgPath, { withFileTypes: true });
        for (const sub of subDirs) {
          if (sub.isDirectory()) {
            const binCandidate = join(pkgPath, sub.name, "bin", "ffmpeg.exe");
            if (existsSync(binCandidate)) return binCandidate;
          }
        }
      }
    }
  } catch {
    // ignore permission errors
  }
  return null;
}

function resolveToolchain() {
  const home = os.homedir();
  const localAppData = process.env.LOCALAPPDATA || join(home, "AppData", "Local");

  const pythonCandidates = [
    process.env.DEEP_RESEARCH_PYTHON,
    join(localAppData, "Programs", "Python", "Python312", "python.exe"),
    join(localAppData, "Programs", "Python", "Python313", "python.exe"),
    join(localAppData, "Programs", "Python", "Python311", "python.exe"),
    "C:\\Python312\\python.exe",
    "/usr/bin/python3",
    "/opt/homebrew/bin/python3",
  ];
  const pythonPath = findExecutable("python3", pythonCandidates) || findExecutable("python", pythonCandidates);

  const pythonScriptsDir = pythonPath ? join(dirname(pythonPath), "Scripts") : "";
  const ytdlpCandidates = [
    process.env.DEEP_RESEARCH_YTDLP,
    pythonScriptsDir ? join(pythonScriptsDir, "yt-dlp.exe") : null,
    pythonScriptsDir ? join(pythonScriptsDir, "yt-dlp") : null,
  ];
  const ytdlpPath = findExecutable("yt-dlp", ytdlpCandidates);

  const ffmpegCandidates = [
    process.env.DEEP_RESEARCH_FFMPEG,
    findWinGetFfmpeg(),
    "C:\\ffmpeg\\bin\\ffmpeg.exe",
    "/opt/homebrew/bin/ffmpeg",
    "/usr/bin/ffmpeg",
  ];
  const ffmpegPath = findExecutable("ffmpeg", ffmpegCandidates);

  return { pythonPath, ytdlpPath, ffmpegPath };
}

function runDoctor() {
  const tools = resolveToolchain();
  let pythonVersion = null;
  let packages = {};

  if (tools.pythonPath) {
    const v = spawnSync(tools.pythonPath, ["--version"], { encoding: "utf8" });
    pythonVersion = (v.stdout || v.stderr || "").trim();

    const pkgCheck = spawnSync(
      tools.pythonPath,
      [
        "-c",
        "import json; pkgs=['youtube_transcript_api','yt_dlp','requests','lxml']; res={}; [res.update({p: True}) if __import__(p) else None for p in pkgs if not False]; print(json.dumps(res))",
      ],
      { encoding: "utf8" }
    );
    if (pkgCheck.status === 0 && pkgCheck.stdout) {
      try {
        packages = JSON.parse(pkgCheck.stdout.trim());
      } catch {
        packages = { raw: pkgCheck.stdout.trim() };
      }
    } else {
      // Check one by one safely
      const safeCheck = spawnSync(
        tools.pythonPath,
        [
          "-c",
          "import json\nres={}\nfor p in ['youtube_transcript_api','yt_dlp','requests','lxml']:\n try:\n  __import__(p); res[p]=True\n except Exception:\n  res[p]=False\nprint(json.dumps(res))",
        ],
        { encoding: "utf8" }
      );
      if (safeCheck.status === 0 && safeCheck.stdout) {
        try {
          packages = JSON.parse(safeCheck.stdout.trim());
        } catch {
          // ignore
        }
      }
    }
  }

  const report = {
    ok: Boolean(tools.pythonPath && tools.ytdlpPath),
    skillRoot: SKILL_ROOT,
    nodeVersion: process.version,
    pythonPath: tools.pythonPath,
    pythonVersion,
    ytdlpPath: tools.ytdlpPath,
    ffmpegPath: tools.ffmpegPath,
    pythonPackages: packages,
  };

  console.log(JSON.stringify(report, null, 2));
  process.exit(report.ok ? 0 : 1);
}

function initWorkspace(args) {
  const targetDirArg = args[0];
  if (!targetDirArg) {
    console.error("Usage: node research_cli.mjs init <workspace_dir> [--topic \"Topic Name\"]");
    process.exit(2);
  }

  let topic = "Deep Research Topic";
  for (let i = 1; i < args.length; i++) {
    if (args[i] === "--topic" && args[i + 1]) {
      topic = args[i + 1];
      i++;
    }
  }

  const ws = resolve(targetDirArg);
  const dirs = [
    ws,
    join(ws, "01_raw_sources"),
    join(ws, "01_raw_sources", "keyframes"),
    join(ws, "02_extracted_notes"),
    join(ws, "03_playbooks"),
  ];
  for (const d of dirs) {
    if (!existsSync(d)) mkdirSync(d, { recursive: true });
  }

  const auditTrailPath = join(ws, "audit_trail.tsv");
  const templateTsv = join(SKILL_ROOT, "resources", "audit_trail_template.tsv");
  if (!existsSync(auditTrailPath)) {
    if (existsSync(templateTsv)) {
      copyFileSync(templateTsv, auditTrailPath);
    } else {
      writeFileSync(
        auditTrailPath,
        "ts\tphase\tsource_id\ttier\tevidence_path\tstatus\tnote\n",
        "utf8"
      );
    }
  }

  const manifestPath = join(ws, "01_raw_sources", "sources_manifest.json");
  if (!existsSync(manifestPath)) {
    writeFileSync(
      manifestPath,
      JSON.stringify(
        {
          topic,
          createdAt: new Date().toISOString(),
          sources: [],
        },
        null,
        2
      ),
      "utf8"
    );
  }

  const planPath = join(ws, "00_research_plan.md");
  if (!existsSync(planPath)) {
    const now = new Date().toISOString();
    const planContent = `# Research Plan: ${topic}
Created: ${now}

## 1. STORM 3-Perspective Inquiry Matrix (Must define before searching)

### A. Implementer / Power-User Perspective (How to actually build & run it)
- [ ] What are the exact installation, setup, configuration, and permission steps?
- [ ] What exact prompts, templates, CLI commands, and workflow sequences do top practitioners use?
- [ ] How do you move from a one-off task to a reusable skill or automated routine?

### B. Skeptic / Debugger Perspective (Where it breaks & hidden costs)
- [ ] Which marketing claims are unverified or exaggerated compared to real user tests?
- [ ] What are the exact failure modes, rate limits, billing traps, and security risks?
- [ ] Under what conditions does this tool/approach fail, and how do practitioners work around it?

### C. Systems Architect Perspective (Mechanisms & tradeoffs)
- [ ] How does the underlying architecture work (state, memory, sandboxing, tool execution, multi-agent handoff)?
- [ ] How does it compare mechanistically against its top alternatives?

---

## 2. 4-Bucket Discovery Quota
- [ ] **Bucket 1 (Primary/Official):** Official docs, GitHub repos, changelogs, release notes.
- [ ] **Bucket 2 (Hands-on Video Demos):** Full tutorial/workflow videos (transcript + visual keyframe extraction).
- [ ] **Bucket 3 (Expert Deep-Dives):** Technical breakdowns, conference talks, practitioner guides.
- [ ] **Bucket 4 (Community & Failure Modes):** Reddit, HackerNews, GitHub Issues, independent critiques.
`;
    writeFileSync(planPath, planContent, "utf8");
  }

  console.log(
    JSON.stringify(
      {
        ok: true,
        workspace: ws,
        created: [
          "00_research_plan.md",
          "01_raw_sources/sources_manifest.json",
          "01_raw_sources/keyframes/",
          "02_extracted_notes/",
          "03_playbooks/",
          "audit_trail.tsv",
        ],
      },
      null,
      2
    )
  );
}

function delegatePythonScript(scriptName, scriptArgs) {
  const tools = resolveToolchain();
  if (!tools.pythonPath) {
    console.error("ERROR: Python 3 executable could not be found.");
    process.exit(1);
  }

  const scriptPath = join(__dirname, scriptName);
  const env = { ...process.env };
  if (tools.ytdlpPath) env.DEEP_RESEARCH_YTDLP = tools.ytdlpPath;
  if (tools.ffmpegPath) env.DEEP_RESEARCH_FFMPEG = tools.ffmpegPath;

  // Prepend Python and FFmpeg directories to PATH so subprocesses inside Python also find them
  const extraPaths = [dirname(tools.pythonPath), join(dirname(tools.pythonPath), "Scripts")];
  if (tools.ffmpegPath) extraPaths.push(dirname(tools.ffmpegPath));
  const pathSep = process.platform === "win32" ? ";" : ":";
  env.PATH = extraPaths.join(pathSep) + pathSep + (env.PATH || "");
  env.PYTHONIOENCODING = "utf-8";

  const result = spawnSync(tools.pythonPath, [scriptPath, ...scriptArgs], {
    stdio: "inherit",
    env,
  });
  process.exit(result.status ?? 1);
}

function installToTarget(args) {
  const targetDirArg = args[0];
  if (!targetDirArg) {
    console.error("Usage: node research_cli.mjs install <target_skill_dir>");
    console.error("Example (OpenBot/Muse/Codex): node research_cli.mjs install ./.agents/skills/deep-researching");
    console.error("Example (Claude Code):        node research_cli.mjs install ./.claude/skills/deep-researching");
    console.error("Example (Hermes Agent):       node research_cli.mjs install ~/.hermes/skills/deep-researching");
    process.exit(2);
  }

  const destResolved = resolve(targetDirArg.replace(/^~(?=$|\/|\\)/, os.homedir()));
  if (destResolved.toLowerCase() === SKILL_ROOT.toLowerCase()) {
    console.log(JSON.stringify({ ok: true, path: destResolved, status: "already_in_place" }, null, 2));
    return;
  }

  mkdirSync(destResolved, { recursive: true });
  cpSync(SKILL_ROOT, destResolved, {
    recursive: true,
    force: true,
    filter: (src) => !src.includes("__pycache__") && !src.includes(".git"),
  });

  console.log(
    JSON.stringify(
      {
        ok: true,
        skill: "deep-researching",
        installed_to: destResolved,
      },
      null,
      2
    )
  );
}

function printHelp() {
  console.log(`deep-researching CLI dispatcher v3.0 (research_cli.mjs)

Usage:
  node research_cli.mjs doctor
  node research_cli.mjs install <target_skill_dir>
  node research_cli.mjs init <workspace_dir> [--topic "Topic Name"]
  node research_cli.mjs discover "<topic>" --out <workspace_dir> [--queries "q1" "q2"] [--auto-ingest]
  node research_cli.mjs yt <video_url_or_id...> --out <workspace_dir> [--keyframes] [--max-keyframes 6] [--auto-snowball]
  node research_cli.mjs web <url...> --out <workspace_dir> [--workers 4]
  node research_cli.mjs audit <workspace_dir> [--min-sources 10] [--min-playbooks 3]
`);
}

const [, , cmd, ...rest] = process.argv;

switch (cmd) {
  case "doctor":
    runDoctor();
    break;
  case "install":
    installToTarget(rest);
    break;
  case "init":
    initWorkspace(rest);
    break;
  case "discover":
    delegatePythonScript("discover_sources.py", rest);
    break;
  case "yt":
    delegatePythonScript("yt_ingest.py", rest);
    break;
  case "web":
    delegatePythonScript("web_ingest.py", rest);
    break;
  case "audit":
    delegatePythonScript("audit_report.py", rest);
    break;
  default:
    printHelp();
    process.exit(cmd === "--help" || cmd === "-h" ? 0 : 2);
}
