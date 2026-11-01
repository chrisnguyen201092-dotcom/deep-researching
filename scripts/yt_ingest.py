#!/usr/bin/env python3
"""
Multi-Tier YouTube Deep Ingestion Tool (`yt_ingest.py` v2.0)
- Tier 1: youtube-transcript-api (v1.x and v0.6.x compatible)
- Tier 2: yt-dlp subtitle URL extraction (JSON3 / VTT fallback)
- Tier 3: Explicit evidence-level tagging when captions are disabled
- V2 Upgrades:
  1. Smart Screen-Share Keyframe Selector: Probes (T+2s, T+5s) after visual cues and selects the frame
     with the highest high-frequency UI/text detail (filtering out low-entropy talking-head A-roll shots).
  2. Primary vs. Affiliate Link Classifier + `--auto-snowball` automatic web ingestion of primary docs.
  3. Multi-threaded parallel video & keyframe processing (`ThreadPoolExecutor`) with thread-safe manifest locks.
"""

import argparse
import concurrent.futures
import datetime
import html
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
import yt_dlp

MANIFEST_LOCK = threading.Lock()
TRANSCRIPT_LOCK = threading.Lock()
_LAST_TRANSCRIPT_FETCH_TS = 0.0

VISUAL_CUE_PATTERNS = [
    r"\bon (?:my |the )?screen\b",
    r"\blook at (?:this|the)\b",
    r"\bas you can see\b",
    r"\bhere you (?:can )?see\b",
    r"\bthis prompt\b",
    r"\bthis config(?:uration)?\b",
    r"\bclick (?:on |here|the |connect|test run|share|publish)\b",
    r"\bin the (?:top |bottom )?(?:left|right) (?:sidebar|panel|corner)\b",
    r"\bopen (?:up )?the (?:routines|marketplace|settings)\b",
    r"\bin the settings\b",
    r"\binside (?:the |our )?(?:app|dashboard|workspace|terminal|editor)\b",
    r"\barchitecture diagram\b",
    r"\bon this slide\b",
    r"\btrên màn hình\b",
    r"\bnhư các bạn thấy\b",
    r"\bbấm vào\b",
]
VISUAL_CUE_REGEX = re.compile("|".join(VISUAL_CUE_PATTERNS), re.IGNORECASE)
URL_REGEX = re.compile(r"https?://[^\s<>\"\'\)\]]+")

AFFILIATE_AND_NOISE_DOMAINS = (
    "bit.ly",
    "tinyurl.com",
    "amzn.to",
    "amazon.com/shop",
    "instagram.com",
    "tiktok.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
    "skool.com",
    "gohighlevel.com",
    "hostinger.com",
    "bluehost.com",
    "webull.com",
    "riverside.fm",
    "patreon.com",
    "buymeacoffee.com",
    "linktr.ee",
    "imp.i115008.net",
    "clstk.com",
)


def classify_outbound_links(urls: List[str]) -> Tuple[List[str], List[str]]:
    """Separate high-value technical/documentation links from affiliate/social/promo noise."""
    primary_docs: List[str] = []
    promo_or_social: List[str] = []

    for raw_url in urls:
        u = raw_url.rstrip(".,;:!)")
        parsed = urlparse(u)
        host = (parsed.netloc or "").lower().replace("www.", "")
        path_lower = (parsed.path or "").lower()

        if not host or "." not in host or len(u) < 12:
            continue

        is_noise = False
        for bad in AFFILIATE_AND_NOISE_DOMAINS:
            if bad in f"{host}{path_lower}":
                is_noise = True
                break
        if any(k in u.lower() for k in ("affiliate", "sponsor", "discount", "exclusiveoffer", "sub_confirmation")):
            is_noise = True

        if is_noise:
            promo_or_social.append(u)
        else:
            primary_docs.append(u)

    return sorted(set(primary_docs)), sorted(set(promo_or_social))


def extract_video_id(url_or_id: str) -> str:
    s = url_or_id.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/|/live/)([A-Za-z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, s)
        if m:
            return m.group(1)
    raise ValueError(f"Could not extract 11-char YouTube video ID from: {url_or_id}")


def format_ts(seconds: float) -> str:
    total = max(0, int(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_ts_str(ts_str: str) -> float:
    parts = [int(p) for p in ts_str.strip().split(":") if p.strip().isdigit()]
    if len(parts) == 3:
        return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    if len(parts) == 2:
        return float(parts[0] * 60 + parts[1])
    return 0.0


def load_cached_transcript_from_disk(raw_dir: Path, video_id: str) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """
    Re-use verified transcript from disk cache if available:
    1. Check `.cache/yt_<vid>_segments.json` for exact sub-second segment objects.
    2. Fallback: parse `- **[MM:SS]** text` blocks from `yt_<vid>.md` and interpolate ~12-word chunks
       across each 45-second block so visual cue timestamps remain accurate within ~2-3 seconds.
    """
    cache_json = raw_dir / ".cache" / f"yt_{video_id}_segments.json"
    if cache_json.exists():
        try:
            segs = json.loads(cache_json.read_text(encoding="utf-8"))
            if isinstance(segs, list) and len(segs) > 0:
                return segs, "disk_cache_json_verified"
        except Exception:
            pass

    md_path = raw_dir / f"yt_{video_id}.md"
    if not md_path.exists():
        return None, "no_disk_cache"

    try:
        content = md_path.read_text(encoding="utf-8", errors="replace")
        bullet_re = re.compile(r"^- \*\*\[(\d{2}:\d{2}(?::\d{2})?)\]\*\*\s+(.+)$", re.MULTILINE)
        matches = bullet_re.findall(content)
        if not matches:
            return None, "no_cached_bullets"

        interpolated: List[Dict[str, Any]] = []
        for idx, (ts_s, paragraph) in enumerate(matches):
            block_start = parse_ts_str(ts_s)
            next_start = parse_ts_str(matches[idx + 1][0]) if (idx + 1) < len(matches) else (block_start + 45.0)
            block_span = max(10.0, min(60.0, next_start - block_start))
            words = paragraph.split()
            if not words:
                continue
            chunk_size = 12
            chunks = [" ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)]
            n_chunks = len(chunks)
            for c_idx, chunk_txt in enumerate(chunks):
                seg_start = round(block_start + (c_idx / max(1, n_chunks)) * block_span, 1)
                seg_dur = round(block_span / max(1, n_chunks), 1)
                interpolated.append({"text": chunk_txt, "start": seg_start, "duration": seg_dur})

        total_words = sum(len(s["text"].split()) for s in interpolated)
        if total_words > 50:
            return interpolated, "disk_cache_md_verified"
    except Exception:
        pass
    return None, "disk_cache_parse_failed"


def save_cached_transcript_to_disk(raw_dir: Path, video_id: str, segments: List[Dict[str, Any]]) -> None:
    try:
        cache_dir = raw_dir / ".cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_json = cache_dir / f"yt_{video_id}_segments.json"
        cache_json.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def fetch_metadata_ytdlp(video_id: str) -> Dict[str, Any]:
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "js_runtimes": {"node": {}},
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info or {}


def fetch_transcript_tier1(video_id: str, lang_prefs: List[str]) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Tier 1: youtube_transcript_api with rate-limit pacing to prevent HTTP 429 IpBlocked."""
    global _LAST_TRANSCRIPT_FETCH_TS
    with TRANSCRIPT_LOCK:
        elapsed = time.time() - _LAST_TRANSCRIPT_FETCH_TS
        if elapsed < 1.5:
            time.sleep(1.5 - elapsed)
        _LAST_TRANSCRIPT_FETCH_TS = time.time()

        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            if hasattr(YouTubeTranscriptApi, "fetch"):
                ytt = YouTubeTranscriptApi()
                try:
                    tlist = ytt.list(video_id)
                    transcript_obj = None
                    for fn in (tlist.find_manually_created_transcript, tlist.find_generated_transcript):
                        try:
                            transcript_obj = fn(lang_prefs)
                            break
                        except Exception:
                            pass
                    if transcript_obj is None:
                        for t in tlist:
                            transcript_obj = t
                            break
                    if transcript_obj is not None:
                        fetched = transcript_obj.fetch()
                        raw = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
                        return raw, f"tier1_ytt_v1 ({getattr(transcript_obj, 'language_code', 'auto')})"
                except Exception as inner_e:
                    err_name = type(inner_e).__name__
                    if "IpBlocked" in err_name or "429" in str(inner_e):
                        return None, f"tier1_rate_limited_429: {err_name}"
                    fetched = ytt.fetch(video_id, languages=lang_prefs)
                    raw = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
                    return raw, "tier1_ytt_v1_direct"

            if hasattr(YouTubeTranscriptApi, "get_transcript"):
                raw = YouTubeTranscriptApi.get_transcript(video_id, languages=lang_prefs)
                return raw, "tier1_ytt_legacy"
        except Exception as e:
            return None, f"tier1_failed: {type(e).__name__}: {e}"
    return None, "tier1_unavailable"


def parse_json3_captions(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
        if not text:
            continue
        start = float(ev.get("tStartMs", 0)) / 1000.0
        dur = float(ev.get("dDurationMs", 0)) / 1000.0
        segments.append({"text": html.unescape(text), "start": start, "duration": dur})
    return segments


def fetch_transcript_tier2_ytdlp(info: Dict[str, Any], lang_prefs: List[str]) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """Tier 2: Extract captions from yt-dlp info dict (subtitles or automatic_captions)."""
    for source_key in ("subtitles", "automatic_captions"):
        tracks_by_lang = info.get(source_key) or {}
        if not tracks_by_lang:
            continue
        candidate_langs = [l for l in lang_prefs if l in tracks_by_lang]
        if not candidate_langs:
            candidate_langs = list(tracks_by_lang.keys())[:2]
        for lang in candidate_langs:
            formats = tracks_by_lang.get(lang) or []
            json3_fmt = next((f for f in formats if f.get("ext") == "json3" and f.get("url")), None)
            if json3_fmt:
                try:
                    resp = requests.get(json3_fmt["url"], timeout=20)
                    if resp.status_code == 200:
                        segs = parse_json3_captions(resp.json())
                        if segs:
                            return segs, f"tier2_ytdlp_{source_key}_{lang}"
                except Exception:
                    pass
    return None, "tier2_no_captions_found"


def fetch_transcript_tier3_whisper_asr(
    video_id: str, raw_dir: Path
) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """
    Tier 3 ASR Fallback for Zero-Caption Videos:
    Downloads a lightweight low-bitrate audio stream (<15 MB) and transcribes it using:
    1. Groq / OpenAI Whisper API (`GROQ_API_KEY` or `OPENAI_API_KEY` in env), or
    2. Local `faster_whisper` / `whisper` Python package if installed.
    """
    groq_key = os.environ.get("GROQ_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    has_faster_whisper = False
    try:
        import faster_whisper  # type: ignore

        has_faster_whisper = True
    except Exception:
        pass

    if not (groq_key or openai_key or has_faster_whisper):
        return None, "tier3_asr_skipped_no_whisper_engine"

    cache_dir = raw_dir / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    audio_path = cache_dir / f"yt_{video_id}_audio.m4a"

    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio[abr<=64][filesize<24M]/worstaudio[filesize<24M]/worstaudio",
            "outtmpl": str(audio_path),
            "overwrites": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        if not audio_path.exists() or audio_path.stat().st_size < 1000:
            return None, "tier3_asr_audio_download_failed"

        # Option A: Cloud Whisper API (Groq or OpenAI)
        if groq_key or openai_key:
            api_url = (
                "https://api.groq.com/openai/v1/audio/transcriptions"
                if groq_key
                else "https://api.openai.com/v1/audio/transcriptions"
            )
            api_key = groq_key or openai_key
            model_name = "whisper-large-v3-turbo" if groq_key else "whisper-1"
            with audio_path.open("rb") as af:
                resp = requests.post(
                    api_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (audio_path.name, af, "audio/mp4")},
                    data={"model": model_name, "response_format": "verbose_json"},
                    timeout=180,
                )
            if resp.status_code == 200:
                payload = resp.json()
                raw_segs = payload.get("segments") or []
                segs = [
                    {
                        "text": str(s.get("text", "")).strip(),
                        "start": float(s.get("start", 0.0)),
                        "duration": max(1.0, float(s.get("end", 0.0)) - float(s.get("start", 0.0))),
                    }
                    for s in raw_segs
                    if str(s.get("text", "")).strip()
                ]
                if segs:
                    return segs, f"tier3_asr_api_{model_name}"

        # Option B: Local faster-whisper
        if has_faster_whisper:
            from faster_whisper import WhisperModel  # type: ignore

            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments_gen, _ = model.transcribe(str(audio_path), beam_size=3)
            segs = [
                {
                    "text": s.text.strip(),
                    "start": float(s.start),
                    "duration": max(1.0, float(s.end - s.start)),
                }
                for s in segments_gen
                if s.text.strip()
            ]
            if segs:
                return segs, "tier3_asr_local_faster_whisper"
    except Exception as e:
        return None, f"tier3_asr_error_{type(e).__name__}"
    finally:
        if audio_path.exists():
            try:
                audio_path.unlink()
            except Exception:
                pass

    return None, "tier3_asr_failed"


def detect_visual_cues(
    segments: List[Dict[str, Any]],
    chapters: Optional[List[Dict[str, Any]]] = None,
    duration: float = 0.0,
    max_cues: int = 12,
    min_gap_sec: float = 35.0,
) -> List[Dict[str, Any]]:
    """
    Hybrid Visual Cue & Silent Slide Transition Detector:
    1. Detects explicit spoken UI/slide cues ('on my screen', 'this prompt', etc.).
    2. Injects creator chapter transitions (start_time + 8s) where new architecture slides or demos appear even when silent.
    3. Covers long un-sampled timeline gaps (>240s) with periodic high-entropy slide probes so silent demos are never missed.
    """
    cues: List[Dict[str, Any]] = []
    last_ts = -999.0
    for seg in segments:
        txt = str(seg.get("text", "")).strip()
        start = float(seg.get("start", 0.0))
        # Skip the first 25 seconds (usually intro hook / talking head)
        if start < 25.0:
            continue
        m = VISUAL_CUE_REGEX.search(txt)
        if m and (start - last_ts) >= min_gap_sec:
            cues.append(
                {
                    "timestamp_sec": round(start, 1),
                    "timestamp_str": format_ts(start),
                    "matched_phrase": m.group(0),
                    "context": txt,
                }
            )
            last_ts = start
            if len(cues) >= max_cues:
                break

    # Supplement with creator chapter transitions if we have remaining keyframe slots
    if chapters and len(cues) < max_cues:
        for ch in chapters:
            ch_start = float(ch.get("start_time", 0.0)) + 8.0
            if ch_start < 30.0 or (duration and ch_start >= duration - 15.0):
                continue
            if all(abs(ch_start - float(c["timestamp_sec"])) >= 45.0 for c in cues):
                cues.append(
                    {
                        "timestamp_sec": round(ch_start, 1),
                        "timestamp_str": format_ts(ch_start),
                        "matched_phrase": "chapter_slide_transition",
                        "context": f"Chapter transition: {ch.get('title', 'Section')}",
                    }
                )
                if len(cues) >= max_cues:
                    break

    # Fallback: If still fewer than 3 cues on a video > 180s, inject periodic silent-slide probes
    if len(cues) < 3 and duration >= 180.0:
        for frac in (0.22, 0.50, 0.78):
            probe_ts = round(duration * frac, 1)
            if probe_ts >= 30.0 and all(abs(probe_ts - float(c["timestamp_sec"])) >= 45.0 for c in cues):
                cues.append(
                    {
                        "timestamp_sec": probe_ts,
                        "timestamp_str": format_ts(probe_ts),
                        "matched_phrase": "silent_slide_entropy_probe",
                        "context": f"Periodic visual slide/UI probe at {int(frac*100)}% timeline",
                    }
                )

    cues.sort(key=lambda x: float(x["timestamp_sec"]))
    return cues[:max_cues]


def _capture_single_frame(
    ffmpeg_bin: str,
    header_str: str,
    stream_url: str,
    sec: int,
    out_file: Path,
) -> int:
    """Capture 1 JPEG frame at `sec` and return its byte size (0 if failed)."""
    cmd = [ffmpeg_bin, "-y"]
    if header_str:
        cmd.extend(["-headers", header_str])
    cmd.extend([
        "-ss",
        str(max(0, sec)),
        "-i",
        stream_url,
        "-frames:v",
        "1",
        "-q:v",
        "3",
        str(out_file),
    ])
    try:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
        if proc.returncode == 0 and out_file.exists():
            return out_file.stat().st_size
    except Exception:
        pass
    return 0


def _capture_best_ui_frame_for_cue(
    ffmpeg_bin: str,
    header_str: str,
    stream_url: str,
    video_id: str,
    base_sec: int,
    duration: float,
    keyframes_dir: Path,
) -> Optional[str]:
    """
    Editors typically cut from the speaker's face (A-roll) to the screen share (B-roll) 2 to 5 seconds
    after the spoken cue ("as you can see"). Furthermore, at fixed JPEG quality (-q:v 3), a dense UI/slide
    screenshot has significantly higher byte entropy than a smooth talking-head studio shot.
    We probe (base_sec + 2) and (base_sec + 5) and keep the higher-detail frame.
    """
    max_sec = max(1, int(duration) - 2) if duration > 10 else base_sec + 10
    cand1_sec = min(max_sec, base_sec + 2)
    cand2_sec = min(max_sec, base_sec + 5)

    final_file = keyframes_dir / f"yt_{video_id}_{cand1_sec:05d}s.jpg"
    if final_file.exists() and final_file.stat().st_size > 15000:
        return str(final_file)

    tmp1 = keyframes_dir / f"_tmp_{video_id}_{cand1_sec}a.jpg"
    tmp2 = keyframes_dir / f"_tmp_{video_id}_{cand2_sec}b.jpg"

    size1 = _capture_single_frame(ffmpeg_bin, header_str, stream_url, cand1_sec, tmp1)
    size2 = _capture_single_frame(ffmpeg_bin, header_str, stream_url, cand2_sec, tmp2) if cand2_sec != cand1_sec else 0

    best_tmp = None
    best_sec = cand1_sec
    if size1 >= size2 and size1 > 2000:
        best_tmp = tmp1
        best_sec = cand1_sec
    elif size2 > size1 and size2 > 2000:
        best_tmp = tmp2
        best_sec = cand2_sec

    out_path: Optional[str] = None
    if best_tmp is not None and best_tmp.exists():
        target = keyframes_dir / f"yt_{video_id}_{best_sec:05d}s.jpg"
        try:
            best_tmp.replace(target)
            out_path = str(target)
        except Exception:
            pass

    for t in (tmp1, tmp2):
        if t.exists():
            try:
                t.unlink()
            except Exception:
                pass

    return out_path


def extract_keyframes_ffmpeg(
    video_id: str,
    info: Dict[str, Any],
    cues: List[Dict[str, Any]],
    keyframes_dir: Path,
    max_keyframes: int = 5,
) -> List[str]:
    ffmpeg_bin = os.environ.get("DEEP_RESEARCH_FFMPEG") or "ffmpeg"
    if not cues:
        return []

    formats = info.get("formats") or []
    video_formats = [
        f
        for f in formats
        if f.get("url")
        and f.get("vcodec") not in (None, "none")
        and (f.get("height") or 0) >= 360
        and (f.get("height") or 0) <= 1080
        and f.get("protocol") in ("https", "http", "m3u8_native")
    ]
    if not video_formats:
        return []

    video_formats.sort(
        key=lambda f: (
            0 if f.get("protocol") == "m3u8_native" else 1,
            abs((f.get("height") or 720) - 720),
        )
    )
    chosen_fmt = video_formats[0]
    stream_url = chosen_fmt["url"]
    headers_dict = chosen_fmt.get("http_headers") or info.get("http_headers") or {}
    header_str = "".join(f"{k}: {v}\r\n" for k, v in headers_dict.items())
    duration = float(info.get("duration") or 0.0)

    target_cues = cues[:max_keyframes]
    saved_paths: List[str] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(target_cues))) as pool:
        futures = [
            pool.submit(
                _capture_best_ui_frame_for_cue,
                ffmpeg_bin,
                header_str,
                stream_url,
                video_id,
                int(cue["timestamp_sec"]),
                duration,
                keyframes_dir,
            )
            for cue in target_cues
        ]
        for fut in futures:
            res = fut.result()
            if res:
                saved_paths.append(res)

    return sorted(saved_paths)


def group_segments_into_sections(
    segments: List[Dict[str, Any]], chapters: Optional[List[Dict[str, Any]]], duration: float
) -> List[Dict[str, Any]]:
    if not segments:
        return []

    sections: List[Dict[str, Any]] = []
    if chapters and len(chapters) > 0:
        for ch in chapters:
            start = float(ch.get("start_time", 0.0))
            end = float(ch.get("end_time", duration or 999999.0))
            title = ch.get("title") or f"Section {format_ts(start)}"
            ch_segs = [s for s in segments if start <= float(s.get("start", 0.0)) < end]
            sections.append(
                {
                    "title": f"[{format_ts(start)} - {format_ts(end)}] {title}",
                    "start": start,
                    "end": end,
                    "segments": ch_segs,
                }
            )
        return sections

    window = 600.0
    max_ts = max(float(s.get("start", 0.0)) for s in segments)
    total_dur = max(duration or 0.0, max_ts + 1.0)
    cur = 0.0
    idx = 1
    while cur < total_dur:
        nxt = cur + window
        win_segs = [s for s in segments if cur <= float(s.get("start", 0.0)) < nxt]
        if win_segs:
            sections.append(
                {
                    "title": f"Part {idx} [{format_ts(cur)} - {format_ts(min(nxt, total_dur))}]",
                    "start": cur,
                    "end": min(nxt, total_dur),
                    "segments": win_segs,
                }
            )
            idx += 1
        cur = nxt
    return sections


def render_section_paragraphs(segments: List[Dict[str, Any]], group_every_sec: float = 45.0) -> str:
    if not segments:
        return "_No spoken transcript in this segment._\n"
    lines: List[str] = []
    buf: List[str] = []
    block_start: Optional[float] = None

    for seg in segments:
        st = float(seg.get("start", 0.0))
        txt = str(seg.get("text", "")).replace("\n", " ").strip()
        if not txt:
            continue
        if block_start is None:
            block_start = st
        buf.append(txt)
        if (st - block_start) >= group_every_sec:
            lines.append(f"- **[{format_ts(block_start)}]** {' '.join(buf)}")
            buf = []
            block_start = None

    if buf and block_start is not None:
        lines.append(f"- **[{format_ts(block_start)}]** {' '.join(buf)}")
    return "\n".join(lines) + "\n"


def update_manifest_and_audit(
    ws: Path,
    source_entry: Dict[str, Any],
    tier_label: str,
    rel_md_path: str,
    status: str,
    note: str,
) -> None:
    with MANIFEST_LOCK:
        manifest_path = ws / "01_raw_sources" / "sources_manifest.json"
        manifest: Dict[str, Any] = {"topic": "Research", "createdAt": "", "sources": []}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        sources = [s for s in manifest.get("sources", []) if s.get("id") != source_entry["id"]]
        sources.append(source_entry)
        manifest["sources"] = sources
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        audit_path = ws / "audit_trail.tsv"
        if not audit_path.exists():
            audit_path.write_text("ts\tphase\tsource_id\ttier\tevidence_path\tstatus\tnote\n", encoding="utf-8")
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        clean_note = note.replace("\t", " ").replace("\n", " ").strip()
        row = f"{now}\tingest_yt\t{source_entry['id']}\t{tier_label}\t{rel_md_path}\t{status}\t{clean_note}\n"
        with audit_path.open("a", encoding="utf-8") as f:
            f.write(row)


def process_video(
    url_or_id: str,
    ws: Path,
    lang_prefs: List[str],
    extract_frames: bool,
    max_keyframes: int,
    auto_snowball: bool = False,
    max_snowball: int = 2,
) -> Dict[str, Any]:
    vid = extract_video_id(url_or_id)
    canonical_url = f"https://www.youtube.com/watch?v={vid}"
    raw_dir = ws / "01_raw_sources"
    keyframes_dir = raw_dir / "keyframes"
    raw_dir.mkdir(parents=True, exist_ok=True)
    keyframes_dir.mkdir(parents=True, exist_ok=True)

    info: Dict[str, Any] = {}
    meta_error = None
    try:
        info = fetch_metadata_ytdlp(vid)
    except Exception as e:
        meta_error = str(e)

    title = info.get("title") or f"YouTube Video {vid}"
    channel = info.get("uploader") or info.get("channel") or "Unknown Channel"
    upload_date = info.get("upload_date") or "Unknown Date"
    duration = float(info.get("duration") or 0.0)
    view_count = info.get("view_count") or 0
    description = info.get("description") or ""
    chapters = info.get("chapters") or []

    all_links = sorted(set(URL_REGEX.findall(description)))
    primary_snowball_links, filtered_Noise_links = classify_outbound_links(all_links)

    segments, method_note = load_cached_transcript_from_disk(raw_dir, vid)
    if not segments:
        segments, method_note = fetch_transcript_tier1(vid, lang_prefs)
        if not segments and info and "429" not in method_note:
            segments, method_note = fetch_transcript_tier2_ytdlp(info, lang_prefs)
        if not segments:
            segments, asr_note = fetch_transcript_tier3_whisper_asr(vid, raw_dir)
            if segments:
                method_note = asr_note
        if segments:
            save_cached_transcript_to_disk(raw_dir, vid, segments)

    word_count = sum(len(str(s.get("text", "")).split()) for s in (segments or []))
    evidence_level = "FULL_TRANSCRIPT_VERIFIED" if segments and word_count > 50 else "METADATA_ONLY_NO_SUBS"

    cues = detect_visual_cues(segments or [], chapters=chapters, duration=duration, max_cues=15)
    saved_keyframes: List[str] = []
    if extract_frames and info and cues:
        saved_keyframes = extract_keyframes_ffmpeg(vid, info, cues, keyframes_dir, max_keyframes=max_keyframes)
        if saved_keyframes:
            evidence_level = "FULL_TRANSCRIPT_PLUS_KEYFRAMES"

    sections = group_segments_into_sections(segments or [], chapters, duration)

    out_md_path = raw_dir / f"yt_{vid}.md"
    rel_md_path = f"01_raw_sources/yt_{vid}.md"

    md_lines = [
        f"# [YouTube Source] {title}",
        "",
        "## 1. Provenance & Evidence Status",
        f"- **Source ID:** `yt_{vid}`",
        f"- **URL:** {canonical_url}",
        f"- **Channel / Creator:** {channel}",
        f"- **Upload Date:** {upload_date}",
        f"- **Duration:** {format_ts(duration)} ({int(duration)}s)",
        f"- **Views:** {view_count:,}" if isinstance(view_count, int) else f"- **Views:** {view_count}",
        f"- **Evidence Level:** `{evidence_level}`",
        f"- **Retrieval Method:** `{method_note}`",
        f"- **Transcript Word Count:** {word_count}",
        "",
    ]

    if meta_error:
        md_lines.extend([f"> [!WARNING]\n> Metadata fetch warning: {meta_error}", ""])

    if chapters:
        md_lines.append("## 2. Creator Chapters")
        for ch in chapters:
            st = format_ts(float(ch.get("start_time", 0)))
            et = format_ts(float(ch.get("end_time", 0)))
            md_lines.append(f"- `{st} - {et}`: {ch.get('title', '')}")
        md_lines.append("")

    if primary_snowball_links:
        md_lines.append("## 3. High-Signal Outbound Links (Filtered Primary / Doc Candidates)")
        for lnk in primary_snowball_links[:20]:
            md_lines.append(f"- {lnk}")
        md_lines.append("")

    if cues:
        md_lines.append("## 4. Detected Visual Demo Cue Timestamps")
        for c in cues:
            md_lines.append(
                f"- **`[{c['timestamp_str']}]`** (trigger: *{c['matched_phrase']}*): \"{c['context']}\""
            )
        md_lines.append("")

    if saved_keyframes:
        md_lines.append("## 5. Extracted Visual Keyframe Screenshots")
        for kf in saved_keyframes:
            md_lines.append(f"- `{kf}`")
        md_lines.append("")

    md_lines.append("## 6. Full Description")
    md_lines.append("```text")
    md_lines.append(description[:4000] if description else "(No description)")
    md_lines.append("```")
    md_lines.append("")

    md_lines.append("## 7. Full Timestamped Transcript")
    if sections:
        for sec in sections:
            md_lines.append(f"### {sec['title']}")
            md_lines.append(render_section_paragraphs(sec["segments"]))
    else:
        md_lines.append(
            "> [!CAUTION]\n> **NO TRANSCRIPT AVAILABLE.** This video has no accessible captions. Do NOT fabricate spoken claims; treat this source strictly as `METADATA_ONLY_NO_SUBS`."
        )

    out_md_path.write_text("\n".join(md_lines), encoding="utf-8")

    snowballed_docs: List[str] = []
    if auto_snowball and primary_snowball_links:
        try:
            import web_ingest

            for s_url in primary_snowball_links[:max_snowball]:
                w_res = web_ingest.process_url(s_url, ws)
                if w_res.get("evidence_level") == "FULL_CONTENT_VERIFIED":
                    snowballed_docs.append(w_res["id"])
        except Exception:
            pass

    source_entry = {
        "id": f"yt_{vid}",
        "kind": "youtube",
        "url": canonical_url,
        "title": title,
        "author": channel,
        "date": upload_date,
        "duration_sec": int(duration),
        "evidence_level": evidence_level,
        "retrieval_method": method_note,
        "word_count": word_count,
        "visual_cues_count": len(cues),
        "keyframes": saved_keyframes,
        "snowball_links": primary_snowball_links[:15],
        "filtered_affiliate_links_count": len(filtered_Noise_links),
        "auto_snowballed_ids": snowballed_docs,
        "raw_path": rel_md_path,
        "extracted_note_path": f"02_extracted_notes/yt_{vid}_note.md",
    }

    tier_label = "Direct" if evidence_level.startswith("FULL_TRANSCRIPT") else "Unknown"
    status_label = "VERIFIED_FULL" if evidence_level.startswith("FULL_TRANSCRIPT") else "METADATA_ONLY"
    update_manifest_and_audit(
        ws=ws,
        source_entry=source_entry,
        tier_label=tier_label,
        rel_md_path=rel_md_path,
        status=status_label,
        note=f"{title} ({word_count} words, {len(saved_keyframes)} UI keyframes, {len(primary_snowball_links)} clean links)",
    )
    return source_entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Deep YouTube Transcript & Smart UI Keyframe Ingestion v2.0")
    parser.add_argument("videos", nargs="+", help="YouTube URLs or 11-char video IDs")
    parser.add_argument("--out", required=True, help="Target research workspace directory")
    parser.add_argument("--langs", default="vi,en,en-US,en-GB", help="Comma-separated language codes")
    parser.add_argument("--keyframes", action="store_true", help="Extract Smart FFmpeg UI keyframes at visual cue timestamps")
    parser.add_argument("--max-keyframes", type=int, default=4, help="Max keyframes per video")
    parser.add_argument("--auto-snowball", action="store_true", help="Automatically ingest top primary doc links found in video description")
    parser.add_argument("--max-snowball", type=int, default=2, help="Max snowball links to auto-ingest per video")
    parser.add_argument("--workers", type=int, default=3, help="Concurrent video ingestion workers")
    parser.add_argument("--sleep", type=float, default=0.5, help="Legacy sleep flag (kept for CLI compatibility)")
    args = parser.parse_args()

    ws = Path(args.out).resolve()
    lang_prefs = [l.strip() for l in args.langs.split(",") if l.strip()]

    results: List[Dict[str, Any]] = []
    workers = max(1, min(args.workers, len(args.videos)))

    if workers == 1:
        for v in args.videos:
            try:
                res = process_video(
                    url_or_id=v,
                    ws=ws,
                    lang_prefs=lang_prefs,
                    extract_frames=args.keyframes,
                    max_keyframes=args.max_keyframes,
                    auto_snowball=args.auto_snowball,
                    max_snowball=args.max_snowball,
                )
                results.append({"ok": True, **res})
            except Exception as e:
                results.append({"ok": False, "input": v, "error": f"{type(e).__name__}: {e}"})
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_vid = {
                pool.submit(
                    process_video,
                    v,
                    ws,
                    lang_prefs,
                    args.keyframes,
                    args.max_keyframes,
                    args.auto_snowball,
                    args.max_snowball,
                ): v
                for v in args.videos
            }
            for fut in concurrent.futures.as_completed(future_to_vid):
                v = future_to_vid[fut]
                try:
                    res = fut.result()
                    results.append({"ok": True, **res})
                except Exception as e:
                    results.append({"ok": False, "input": v, "error": f"{type(e).__name__}: {e}"})

    print(json.dumps({"processed": len(results), "results": results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
