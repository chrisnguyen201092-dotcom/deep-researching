#!/usr/bin/env python3
"""
Multi-Bucket Autonomous Source Discovery Engine (`discover_sources.py` v3.0)
Automatically discovers, scores, and deduplicates high-signal sources across all 4 Mandatory Research Buckets
without relying on the LLM's built-in search tool:
- Bucket 1 (Official & GitHub Repos/Docs): GitHub Repositories API + GitHub Issues/Discussions API
- Bucket 2 (Hands-on Video Demos): Multi-angle `yt-dlp` YouTube search (`ytsearch`), filtering out Shorts (<180s)
  and ranking by duration + view velocity + tutorial/workflow density.
- Bucket 3 (Expert Deep-Dives & Technical Blogs): Hacker News Algolia Search API (stories with high points/comments)
  + DuckDuckGo HTML/Lite technical article discovery.
- Bucket 4 (Community Failure Modes & Pitfalls): Reddit JSON Search API + Hacker News comments/issues (`bug`, `limit`, `pitfall`).

Supports `--auto-ingest` to automatically pipe the top-ranked YouTube and Web/GitHub sources into
`yt_ingest.py` and `web_ingest.py`.
"""

import argparse
import concurrent.futures
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlparse

import requests
import yt_dlp

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def search_youtube_bucket(queries: List[str], max_per_query: int = 8, min_duration_sec: int = 180) -> List[Dict[str, Any]]:
    """Search YouTube across multiple query angles using yt-dlp and filter out Shorts/low-content clips."""
    seen_ids = set()
    candidates: List[Dict[str, Any]] = []

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }

    for q in queries:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{max_per_query}:{q}", download=False)
                entries = (info or {}).get("entries") or []
                for e in entries:
                    if not e or not isinstance(e, dict):
                        continue
                    vid = e.get("id")
                    if not vid or vid in seen_ids or len(str(vid)) != 11:
                        continue
                    duration = int(e.get("duration") or 0)
                    if duration and duration < min_duration_sec:
                        continue
                    title = e.get("title") or ""
                    channel = e.get("channel") or e.get("uploader") or "Unknown"
                    views = int(e.get("view_count") or 0)
                    url = f"https://www.youtube.com/watch?v={vid}"

                    # Compute quality score favoring in-depth tutorials/workshops (10-60 mins)
                    dur_bonus = min(30, duration // 60) if duration else 10
                    kw_bonus = 15 if re.search(r"tutorial|workflow|workshop|deep dive|architecture|build|use case|setup|guide", title, re.I) else 0
                    score = dur_bonus + kw_bonus + min(25, int((views ** 0.25) if views > 0 else 5))

                    seen_ids.add(vid)
                    candidates.append(
                        {
                            "bucket": "Bucket 2: Hands-on Video Demos (YouTube)",
                            "type": "youtube",
                            "id": f"yt_{vid}",
                            "url": url,
                            "title": title,
                            "author": channel,
                            "duration_sec": duration,
                            "views": views,
                            "query_matched": q,
                            "quality_score": score,
                        }
                    )
        except Exception:
            continue

    candidates.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
    return candidates


NOISE_QUERY_WORDS = {
    "usage", "and", "best", "use", "cases", "case", "how", "to", "tutorial", "tutorials",
    "guide", "guides", "workflow", "workflows", "architecture", "deep", "dive", "setup",
    "full", "complete", "review", "comparison", "vs", "or", "for", "with", "in", "on",
    "cach", "su", "dung", "huong", "dan", "chi", "tiet", "toan", "dien", "la", "gi",
    "cách", "sử", "dụng", "hướng", "dẫn", "chi", "tiết", "toàn", "diện", "là", "gì",
}


def extract_core_entities(topic: str, extra_queries: Optional[List[str]] = None) -> List[str]:
    """
    Extracts clean tool/product entity names (e.g., ['Grok Bot', 'OpenBot']) from conversational
    or multilingual topic strings like 'Grok Bot / OpenBot usage and best use cases'.
    """
    raw_inputs = [topic] + list(extra_queries or [])
    entities: List[str] = []
    for raw in raw_inputs:
        # Split on slashes, ampersands, commas, 'vs', 'and'
        parts = re.split(r"\s*(?:/|&|,|\bvs\.?\b|\band\b|\bvà\b|\bhoặc\b)\s*", raw, flags=re.I)
        for p in parts:
            tokens = [
                w for w in re.findall(r"[A-Za-z0-9_.-]+", p)
                if w.lower() not in NOISE_QUERY_WORDS and len(w) >= 2
            ]
            if tokens:
                ent = " ".join(tokens[:3]).strip()
                if ent and ent.lower() not in {e.lower() for e in entities}:
                    entities.append(ent)
    if not entities:
        entities = [topic.strip()[:40]]
    return entities[:4]


def _matches_any_entity(text: str, entities: List[str]) -> bool:
    low = text.lower()
    low_compact = re.sub(r"[\s_-]+", "", low)
    for ent in entities:
        ent_low = ent.lower().strip()
        ent_compact = re.sub(r"[\s_-]+", "", ent_low)
        if ent_low in low or (len(ent_compact) >= 5 and ent_compact in low_compact):
            return True
    return False


def search_github_bucket(entities: List[str], max_repos: int = 8, max_issues: int = 6) -> List[Dict[str, Any]]:
    """Search GitHub Repositories and Issues/Discussions using clean entity names and strict title/repo relevance filtering."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github.v3+json"}
    seen_urls = set()
    candidates: List[Dict[str, Any]] = []

    for ent in entities[:3]:
        # 1. Repositories search (exact entity phrase)
        try:
            repo_q = f'"{ent}"' if " " in ent else ent
            r = requests.get(
                f"https://api.github.com/search/repositories?q={quote_plus(repo_q)}&sort=stars&order=desc&per_page={max_repos}",
                headers=headers,
                timeout=12,
            )
            if r.status_code == 200:
                for item in (r.json().get("items") or []):
                    html_url = item.get("html_url")
                    if not html_url or html_url in seen_urls:
                        continue
                    full_name = item.get("full_name") or ""
                    desc = item.get("description") or ""
                    if not _matches_any_entity(f"{full_name} {desc}", entities):
                        continue
                    seen_urls.add(html_url)
                    stars = int(item.get("stargazers_count") or 0)
                    candidates.append(
                        {
                            "bucket": "Bucket 1: Official Docs & GitHub Repositories",
                            "type": "web",
                            "url": html_url,
                            "title": f"GitHub Repo: {full_name} ({stars:,} stars) — {desc[:100]}",
                            "author": (item.get("owner") or {}).get("login") or "github",
                            "stars": stars,
                            "query_matched": ent,
                            "quality_score": 45 + min(40, int((stars ** 0.3) if stars > 0 else 5)),
                        }
                    )
        except Exception:
            pass

        # 2. GitHub Issues / Pitfalls search — require entity in:title so unrelated repos with huge comment bodies never pollute
        try:
            issue_q = f'"{ent}" in:title (bug OR limit OR error OR architecture OR workflow OR agent)'
            r_iss = requests.get(
                f"https://api.github.com/search/issues?q={quote_plus(issue_q)}&sort=comments&order=desc&per_page={max_issues}",
                headers=headers,
                timeout=12,
            )
            if r_iss.status_code == 200:
                for item in (r_iss.json().get("items") or [])[:max_issues]:
                    html_url = item.get("html_url")
                    comments = int(item.get("comments") or 0)
                    title = item.get("title") or ""
                    if not html_url or html_url in seen_urls or comments < 1:
                        continue
                    if not _matches_any_entity(f"{title} {html_url}", entities):
                        continue
                    seen_urls.add(html_url)
                    candidates.append(
                        {
                            "bucket": "Bucket 4: Community Failure Modes & Issues",
                            "type": "web",
                            "url": html_url,
                            "title": f"GitHub Issue ({comments} comments): {title}",
                            "author": (item.get("user") or {}).get("login") or "github-user",
                            "comments": comments,
                            "query_matched": issue_q,
                            "quality_score": 25 + min(30, comments * 2),
                        }
                    )
        except Exception:
            pass

    candidates.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
    return candidates


def search_hackernews_bucket(queries: List[str], max_per_query: int = 8) -> List[Dict[str, Any]]:
    """Query Hacker News Algolia API for high-signal technical articles and community discussions."""
    seen_urls = set()
    candidates: List[Dict[str, Any]] = []

    for q in queries[:3]:
        try:
            api_url = f"https://hn.algolia.com/api/v1/search?query={quote_plus(q)}&tags=story&hitsPerPage={max_per_query}"
            r = requests.get(api_url, headers={"User-Agent": USER_AGENT}, timeout=12)
            if r.status_code != 200:
                continue
            for hit in (r.json().get("hits") or []):
                points = int(hit.get("points") or 0)
                num_comments = int(hit.get("num_comments") or 0)
                if points < 5 and num_comments < 3:
                    continue
                object_id = hit.get("objectID")
                ext_url = hit.get("url")
                hn_discussion_url = f"https://news.ycombinator.com/item?id={object_id}"
                title = hit.get("title") or "HN Post"

                # Add external technical blog post if present (Bucket 3)
                if ext_url and ext_url not in seen_urls and "youtube.com" not in ext_url and "youtu.be" not in ext_url:
                    seen_urls.add(ext_url)
                    candidates.append(
                        {
                            "bucket": "Bucket 3: Expert Deep-Dives & Technical Blogs",
                            "type": "web",
                            "url": ext_url,
                            "title": f"{title} (via HN, {points} pts)",
                            "author": hit.get("author") or "hn",
                            "points": points,
                            "comments": num_comments,
                            "query_matched": q,
                            "quality_score": 25 + min(35, points // 5 + num_comments // 3),
                        }
                    )

                # Add HN discussion thread itself if it has rich community debate (Bucket 4)
                if num_comments >= 10 and hn_discussion_url not in seen_urls:
                    seen_urls.add(hn_discussion_url)
                    candidates.append(
                        {
                            "bucket": "Bucket 4: Community Failure Modes & Issues",
                            "type": "web",
                            "url": hn_discussion_url,
                            "title": f"HN Discussion ({num_comments} comments, {points} pts): {title}",
                            "author": hit.get("author") or "hn",
                            "points": points,
                            "comments": num_comments,
                            "query_matched": q,
                            "quality_score": 20 + min(35, num_comments // 2),
                        }
                    )
        except Exception:
            continue

    candidates.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
    return candidates


def search_reddit_bucket(queries: List[str], max_per_query: int = 8) -> List[Dict[str, Any]]:
    """Query Reddit public JSON search endpoint for real user experiences, bugs, and comparisons."""
    seen_urls = set()
    candidates: List[Dict[str, Any]] = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeepResearchSkill/3.0"}

    for q in queries[:3]:
        try:
            url = f"https://www.reddit.com/search.json?q={quote_plus(q)}&sort=relevance&t=year&limit={max_per_query}"
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                continue
            children = ((r.json().get("data") or {}).get("children")) or []
            for child in children:
                data = child.get("data") or {}
                permalink = data.get("permalink")
                if not permalink:
                    continue
                full_url = f"https://www.reddit.com{permalink}"
                if full_url in seen_urls:
                    continue
                score = int(data.get("score") or 0)
                num_comments = int(data.get("num_comments") or 0)
                if score < 3 and num_comments < 3:
                    continue
                seen_urls.add(full_url)
                sub = data.get("subreddit_name_prefixed") or "r/all"
                title = data.get("title") or "Reddit Thread"
                candidates.append(
                    {
                        "bucket": "Bucket 4: Community Failure Modes & Issues",
                        "type": "web",
                        "url": full_url,
                        "title": f"[{sub}] {title} ({num_comments} comments, {score} upvotes)",
                        "author": data.get("author") or "reddit",
                        "comments": num_comments,
                        "query_matched": q,
                        "quality_score": 20 + min(35, num_comments + score // 5),
                    }
                )
        except Exception:
            continue

    candidates.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
    return candidates


def search_scholar_bucket(entities: List[str], max_per_query: int = 6) -> List[Dict[str, Any]]:
    """
    Scholarly & Canonical Paper Discovery (OpenAlex + arXiv APIs, inspired by Hyperresearch `scholar/`):
    - Queries OpenAlex (`api.openalex.org/works`) sorted by citation count, automatically skipping retracted papers (`is_retracted`).
    - Queries arXiv (`export.arxiv.org/api/query`) for cutting-edge CS/AI/Math preprints.
    - Deduplicates by DOI / normalized title and prefers Open-Access PDF or landing URLs.
    """
    seen_keys = set()
    candidates: List[Dict[str, Any]] = []
    headers = {"User-Agent": f"{USER_AGENT} (mailto:research@openbot.ai)"}

    for ent in entities[:2]:
        # 1. OpenAlex API (citation-ranked works, retraction-filtered)
        try:
            oa_url = (
                f"https://api.openalex.org/works?search={quote_plus(ent)}"
                f"&filter=is_retracted:false&sort=cited_by_count:desc&per_page={max_per_query}"
            )
            r = requests.get(oa_url, headers=headers, timeout=12)
            if r.status_code == 200:
                for item in (r.json().get("results") or []):
                    if item.get("is_retracted"):
                        continue
                    title = (item.get("title") or "").strip()
                    if not title or not _matches_any_entity(title, entities):
                        continue
                    doi = item.get("doi") or ""
                    oa_loc = (
                        (item.get("best_oa_location") or {}).get("url_for_pdf")
                        or (item.get("open_access") or {}).get("oa_url")
                        or doi
                        or item.get("id")
                    )
                    if not oa_loc:
                        continue
                    norm_key = (doi or re.sub(r"\W+", "", title.lower()))[:60]
                    if norm_key in seen_keys:
                        continue
                    seen_keys.add(norm_key)
                    cites = int(item.get("cited_by_count") or 0)
                    year = item.get("publication_year") or ""
                    candidates.append(
                        {
                            "bucket": "Bucket 3: Expert Deep-Dives & Scholarly Papers",
                            "type": "web",
                            "url": oa_loc,
                            "title": f"[Paper {year}, {cites:,} cites] {title}",
                            "author": "OpenAlex",
                            "citations": cites,
                            "doi": doi,
                            "query_matched": ent,
                            "quality_score": 30 + min(40, int((cites ** 0.35) if cites > 0 else 8)),
                        }
                    )
        except Exception:
            pass

        # 2. arXiv API (for AI/CS/Engineering technical papers)
        try:
            arxiv_q = f'ti:"{ent}"' if " " in ent else f"ti:{ent}"
            ax_url = f"http://export.arxiv.org/api/query?search_query={quote_plus(arxiv_q)}&sortBy=relevance&max_results={max_per_query}"
            r_ax = requests.get(ax_url, headers=headers, timeout=12)
            if r_ax.status_code == 200:
                entries = re.findall(r"<entry>([\s\S]*?)</entry>", r_ax.text)
                for entry_xml in entries:
                    id_m = re.search(r"<id>(https?://arxiv\.org/abs/[^\s<]+)</id>", entry_xml)
                    t_m = re.search(r"<title>([\s\S]*?)</title>", entry_xml)
                    if not id_m or not t_m:
                        continue
                    abs_url = id_m.group(1).strip()
                    title = re.sub(r"\s+", " ", t_m.group(1)).strip()
                    if not _matches_any_entity(title, entities):
                        continue
                    norm_key = re.sub(r"\W+", "", title.lower())[:60]
                    if norm_key in seen_keys:
                        continue
                    seen_keys.add(norm_key)
                    candidates.append(
                        {
                            "bucket": "Bucket 3: Expert Deep-Dives & Scholarly Papers",
                            "type": "web",
                            "url": abs_url,
                            "title": f"[arXiv Preprint] {title}",
                            "author": "arXiv",
                            "query_matched": ent,
                            "quality_score": 38,
                        }
                    )
        except Exception:
            pass

    candidates.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
    return candidates


def build_query_variants(topic: str, extra_queries: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """Generate targeted multi-angle search queries for each of the research buckets."""
    entities = extract_core_entities(topic, extra_queries)
    extras = [q.strip() for q in (extra_queries or []) if q.strip()]

    yt_queries: List[str] = []
    for ent in entities[:3]:
        yt_queries.extend(
            [
                f"{ent} full tutorial workflow",
                f"{ent} use cases setup guide",
                f"{ent} architecture deep dive",
            ]
        )
    yt_queries.extend(extras)

    gh_queries = entities
    hn_queries = entities
    reddit_queries = [f"{ent} workflow OR review OR bug" for ent in entities[:2]] + entities
    return {
        "youtube": list(dict.fromkeys(yt_queries)),
        "github": list(dict.fromkeys(gh_queries)),
        "hn": list(dict.fromkeys(hn_queries)),
        "reddit": list(dict.fromkeys(reddit_queries)),
        "scholar": list(dict.fromkeys(entities)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Bucket Autonomous Source Discovery Engine v3.3")
    parser.add_argument("topic", help="Primary research topic or keyword")
    parser.add_argument("--queries", nargs="*", default=[], help="Optional additional search query variants")
    parser.add_argument("--out", required=True, help="Research workspace directory")
    parser.add_argument("--max-yt", type=int, default=15, help="Max YouTube candidates to retain")
    parser.add_argument("--max-web", type=int, default=20, help="Max Web/GitHub/Community/Scholar candidates to retain")
    parser.add_argument("--auto-ingest", action="store_true", help="Automatically ingest top discovered sources")
    parser.add_argument("--ingest-yt-count", type=int, default=8, help="Number of top YouTube videos to auto-ingest")
    parser.add_argument("--ingest-web-count", type=int, default=8, help="Number of top Web/GitHub URLs to auto-ingest")
    args = parser.parse_args()

    ws = Path(args.out).resolve()
    ws.mkdir(parents=True, exist_ok=True)

    q_map = build_query_variants(args.topic, args.queries)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        f_yt = pool.submit(search_youtube_bucket, q_map["youtube"])
        f_gh = pool.submit(search_github_bucket, q_map["github"])
        f_hn = pool.submit(search_hackernews_bucket, q_map["hn"])
        f_rd = pool.submit(search_reddit_bucket, q_map["reddit"])
        f_sc = pool.submit(search_scholar_bucket, q_map["scholar"])

        yt_results = f_yt.result()[: args.max_yt]
        gh_results = f_gh.result()
        hn_results = f_hn.result()
        rd_results = f_rd.result()
        sc_results = f_sc.result()

    # Combine and deduplicate web candidates across Buckets 1, 3, 4 (including Scholarly papers)
    seen_web = set()
    web_results: List[Dict[str, Any]] = []
    for item in gh_results + hn_results + rd_results + sc_results:
        u = item["url"]
        if u not in seen_web:
            seen_web.add(u)
            web_results.append(item)
    web_results.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
    web_results = web_results[: args.max_web]

    all_candidates = yt_results + web_results
    bucket_counts: Dict[str, int] = {}
    for c in all_candidates:
        b = c["bucket"]
        bucket_counts[b] = bucket_counts.get(b, 0) + 1

    payload = {
        "topic": args.topic,
        "discovered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_candidates": len(all_candidates),
        "youtube_candidates_count": len(yt_results),
        "web_candidates_count": len(web_results),
        "bucket_breakdown": bucket_counts,
        "youtube_candidates": yt_results,
        "web_candidates": web_results,
    }

    json_path = ws / "00_discovered_candidates.json"
    md_path = ws / "00_discovered_candidates.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        f"# Discovered Source Candidates: {args.topic}",
        "",
        f"- **Generated At:** `{payload['discovered_at']}`",
        f"- **Total Ranked Candidates:** `{len(all_candidates)}` (`{len(yt_results)}` YouTube Videos + `{len(web_results)}` Web/GitHub/Community Sources)",
        "",
        "## 1. Top YouTube Video Candidates (Bucket 2)",
        "",
        "| Rank | Score | Duration | Views | Title & Channel | URL |",
        "| :---: | :---: | :---: | :---: | :--- | :--- |",
    ]
    for idx, y in enumerate(yt_results, start=1):
        dur_m = f"{y.get('duration_sec', 0) // 60}:{y.get('duration_sec', 0) % 60:02d}"
        md_lines.append(
            f"| {idx} | `{y['quality_score']}` | `{dur_m}` | `{y.get('views', 0):,}` | **{y['title']}** (*{y['author']}*) | {y['url']} |"
        )

    md_lines.extend(
        [
            "",
            "## 2. Top Official Docs, GitHub, Blogs & Community Candidates (Buckets 1, 3, 4)",
            "",
            "| Rank | Score | Bucket | Title | URL |",
            "| :---: | :---: | :--- | :--- | :--- |",
        ]
    )
    for idx, w in enumerate(web_results, start=1):
        md_lines.append(f"| {idx} | `{w['quality_score']}` | `{w['bucket']}` | **{w['title']}** | {w['url']} |")

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    auto_ingest_summary: Dict[str, Any] = {}
    if args.auto_ingest:
        scripts_dir = Path(__file__).resolve().parent
        top_yt_urls = [y["url"] for y in yt_results[: args.ingest_yt_count]]
        top_web_urls = [w["url"] for w in web_results[: args.ingest_web_count]]

        if top_yt_urls:
            yt_cmd = [
                sys.executable,
                str(scripts_dir / "yt_ingest.py"),
                *top_yt_urls,
                "--out",
                str(ws),
                "--keyframes",
                "--max-keyframes",
                "3",
                "--auto-snowball",
                "--workers",
                "3",
            ]
            subprocess.run(yt_cmd, check=False)
            auto_ingest_summary["ingested_yt_urls"] = top_yt_urls

        if top_web_urls:
            web_cmd = [
                sys.executable,
                str(scripts_dir / "web_ingest.py"),
                *top_web_urls,
                "--out",
                str(ws),
                "--workers",
                "4",
            ]
            subprocess.run(web_cmd, check=False)
            auto_ingest_summary["ingested_web_urls"] = top_web_urls

    print(
        json.dumps(
            {
                "status": "ok",
                "candidates_json": str(json_path),
                "candidates_md": str(md_path),
                "total_candidates": len(all_candidates),
                "youtube_count": len(yt_results),
                "web_count": len(web_results),
                "bucket_breakdown": bucket_counts,
                "auto_ingest": auto_ingest_summary,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
