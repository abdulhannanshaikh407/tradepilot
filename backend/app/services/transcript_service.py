# app/services/transcript_service.py
"""Fetch real YouTube transcripts with graceful degradation.

Uses multiple sources in order:
  1. yt-dlp auto-subtitles (works from most cloud servers)
  2. Invidious API (free, works from cloud servers) — fetched in parallel
  3. youtube-transcript-api (works from residential IPs)
  4. Optional paid transcript API (if SUPADATA_API_KEY env var is set)
  5. Simulated demo transcript (last resort fallback)
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from typing import Dict, Optional

import httpx

from app.services.youtube_service import SAMPLE_TRANSCRIPTS, demo_transcript_for, fetch_video_metadata

logger = logging.getLogger("tradepilot.transcript")

class TranscriptError(Exception):
    def __init__(self, message: str, code: str = "transcript_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _clean_text(segment: str) -> str:
    text = re.sub(r"\[.*?\]", "", segment)
    text = re.sub(r"\(.*?\)", " ", text)
    text = text.replace("\n", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


# Updated Invidious instances (2024-2026 working instances)
INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://iv.ggtyler.dev",
    "https://invidious.perennialte.ch",
    "https://yt.artemislena.eu",
    "https://invidious.privacyredirect.com",
    "https://invidious.fdn.fr",
    "https://vid.puffyan.us",
    "https://invidious.lunar.icu",
    "https://invidious.protokoll-11.de",
]


def _fetch_via_ytdlp(video_id: str) -> Optional[str]:
    """Source 1: Use yt-dlp to pull auto-generated captions.

    yt-dlp --write-auto-sub --skip-download fetches .vtt subtitle files.
    This tends to survive YouTube's datacenter IP blocking better than
    youtube-transcript-api because it mimics a normal browser request.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [
                "yt-dlp",
                "--write-auto-sub",
                "--sub-lang", "en",
                "--sub-format", "vtt",
                "--skip-download",
                "--no-warnings",
                "--quiet",
                "-o", os.path.join(tmpdir, "%(id)s.%(ext)s"),
                f"https://www.youtube.com/watch?v={video_id}",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                logger.debug("yt-dlp failed for %s: %s", video_id, result.stderr[:200])
                return None

            # Find the .vtt file
            vtt_files = [f for f in os.listdir(tmpdir) if f.endswith(".vtt")]
            if not vtt_files:
                return None

            vtt_path = os.path.join(tmpdir, vtt_files[0])
            with open(vtt_path, "r", encoding="utf-8") as f:
                vtt_content = f.read()

            # Parse VTT: strip timestamps and formatting tags
            lines = []
            seen = set()
            for line in vtt_content.split("\n"):
                line = line.strip()
                # Skip timestamps, empty lines, headers
                if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
                    continue
                if "-->" in line:
                    continue
                if re.match(r"^\d+$", line):
                    continue
                # Strip VTT formatting tags
                clean = re.sub(r"<[^>]+>", "", line)
                clean = re.sub(r"\{[^}]+\}", "", clean)
                clean = clean.strip()
                if clean and clean not in seen:
                    seen.add(clean)
                    lines.append(clean)

            transcript = " ".join(lines)
            if len(transcript) > 50:
                logger.info("Transcript fetched via yt-dlp for %s", video_id)
                return _clean_text(transcript)

    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp timed out for video %s", video_id)
    except Exception as exc:
        logger.debug("yt-dlp error for %s: %s", video_id, exc)

    return None


def _fetch_single_invidious(instance: str, video_id: str) -> Optional[str]:
    """Fetch transcript from a single Invidious instance. Returns transcript or None."""
    try:
        # Get captions list
        url = f"{instance}/api/v1/captions/{video_id}"
        resp = httpx.get(url, timeout=5, follow_redirects=True)
        if resp.status_code != 200:
            return None

        captions = resp.json()
        if not captions or not isinstance(captions, list):
            return None

        # Find English caption (prefer manual over auto-generated)
        caption_url = None
        for cap in captions:
            lang = (cap.get("language_code") or "").lower()
            if lang.startswith("en"):
                caption_url = cap.get("url")
                if cap.get("kind") != "asr":  # Prefer manual subs
                    break

        if not caption_url and captions:
            caption_url = captions[0].get("url")

        if not caption_url:
            return None

        # Fetch the actual transcript
        if caption_url.startswith("/"):
            caption_url = f"{instance}{caption_url}"

        # Request JSON format if possible
        if "?" in caption_url:
            caption_url += "&fmt=json3"
        else:
            caption_url += "?fmt=json3"

        t_resp = httpx.get(caption_url, timeout=5, follow_redirects=True)
        if t_resp.status_code != 200:
            # Try without fmt parameter
            clean_url = caption_url.split("?")[0]
            t_resp = httpx.get(clean_url, timeout=5, follow_redirects=True)
            if t_resp.status_code != 200:
                return None

        content_type = t_resp.headers.get("content-type", "")

        # Parse JSON3 format
        if "json" in content_type or t_resp.text.strip().startswith("{"):
            try:
                data = t_resp.json()
                events = data.get("events", [])
                parts = []
                for event in events:
                    segs = event.get("segs", [])
                    for seg in segs:
                        text = seg.get("utf8", "").strip()
                        if text and text != "\n":
                            parts.append(text)
                transcript = " ".join(parts)
                if transcript.strip():
                    return _clean_text(transcript)
            except (json.JSONDecodeError, KeyError):
                pass

        # Parse XML format (VTT/SRT)
        text = t_resp.text
        clean = re.sub(r"<[^>]+>", " ", text)
        clean = re.sub(r"&amp;", "&", clean)
        clean = re.sub(r"&#39;", "'", clean)
        clean = re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}", "", clean)
        clean = re.sub(r"\d+\s*$", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) > 50:
            return _clean_text(clean)

    except Exception:
        pass

    return None


def _fetch_via_invidious(video_id: str) -> Optional[str]:
    """Fetch transcript via free Invidious API instances — tried in parallel for speed."""
    with ThreadPoolExecutor(max_workers=min(len(INVIDIOUS_INSTANCES), 8)) as executor:
        future_to_instance = {
            executor.submit(_fetch_single_invidious, instance, video_id): instance
            for instance in INVIDIOUS_INSTANCES
        }
        try:
            for future in as_completed(future_to_instance, timeout=12):
                instance = future_to_instance[future]
                try:
                    result = future.result(timeout=1)
                    if result:
                        # Cancel remaining futures
                        for f in future_to_instance:
                            f.cancel()
                        logger.info("Transcript fetched from %s", instance)
                        return result
                except Exception:
                    continue
        except (FuturesTimeoutError, Exception):
            logger.warning("All Invidious instances timed out for video %s", video_id)

    return None


def _fetch_with_api(video_id: str) -> Optional[list]:
    """Fallback: youtube-transcript-api (may fail from cloud IPs)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        if hasattr(YouTubeTranscriptApi, "fetch"):
            api = YouTubeTranscriptApi()
            transcript = api.fetch(video_id)
            if hasattr(transcript, "to_raw_data"):
                return transcript.to_raw_data()
            return transcript
        captions = YouTubeTranscriptApi().list(video_id)
        return captions.find_generated_transcript().fetch()
    except Exception:
        return None


def _fetch_via_supadata(video_id: str) -> Optional[str]:
    """Optional paid transcript API (SUPADATA_API_KEY). $2-5/mo, very reliable."""
    api_key = os.environ.get("SUPADATA_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        resp = httpx.get(
            f"https://api.supadata.ai/v1/youtube/transcript",
            params={"videoId": video_id, "lang": "en"},
            headers={"x-api-key": api_key},
            timeout=10,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            data = resp.json()
            text = data.get("transcript", "")
            if not text and isinstance(data.get("content"), list):
                text = " ".join(seg.get("text", "") for seg in data["content"])
            if text and len(text) > 50:
                logger.info("Transcript fetched via Supadata API for %s", video_id)
                return _clean_text(text)
    except Exception as exc:
        logger.debug("Supadata API error for %s: %s", video_id, exc)
    return None


def fetch_transcript(video_id: str, language_hint: Optional[str] = None) -> dict:
    """Fetch a real transcript. Returns dict(transcript, language, is_demo=False, reason=...).

    Fallback chain:
      1. yt-dlp (best cloud compatibility)
      2. Invidious (parallel, free)
      3. youtube-transcript-api (residential IPs)
      4. Supadata API (optional, gated by SUPADATA_API_KEY)
      5. Raises TranscriptError if all real paths fail
    """
    reasons = []

    # Source 1: yt-dlp (works from most cloud servers)
    transcript_text = _fetch_via_ytdlp(video_id)
    if transcript_text:
        return {"transcript": transcript_text, "language": "en", "is_demo": False, "reason": ""}

    reasons.append("yt-dlp: captions not available or download failed")

    # Source 2: Invidious API (works from cloud servers)
    transcript_text = _fetch_via_invidious(video_id)
    if transcript_text:
        return {"transcript": transcript_text, "language": "en", "is_demo": False, "reason": ""}

    reasons.append("Invidious: all instances timed out or returned no captions")

    # Source 3: youtube-transcript-api (may work from residential IPs)
    raw = _fetch_with_api(video_id)
    if raw:
        parts = []
        for segment in raw:
            text = segment.get("text", "") if isinstance(segment, dict) else str(segment)
            if text:
                parts.append(_clean_text(text))
        transcript = " ".join(parts)
        if transcript.strip():
            return {"transcript": transcript, "language": "original", "is_demo": False, "reason": ""}

    reasons.append("youtube-transcript-api: blocked or unavailable from this IP")

    # Source 4: Supadata API (optional paid fallback)
    transcript_text = _fetch_via_supadata(video_id)
    if transcript_text:
        return {"transcript": transcript_text, "language": "en", "is_demo": False, "reason": ""}

    reasons.append("Supadata API: not configured or failed")

    raise TranscriptError(
        "Could not retrieve a transcript for this video.",
        code="no_transcript",
    )


def get_transcript(
    video_id: str,
    url: str,
    allow_demo_fallback: bool = True,
    hint: Optional[str] = None,
) -> Dict:
    """Public entry point used by the YouTube route."""
    # Fetch transcript and metadata in parallel for speed
    metadata = {"video_title": "YouTube video"}
    transcript_result = None
    transcript_error = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        meta_future = executor.submit(fetch_video_metadata, video_id)
        transcript_future = executor.submit(fetch_transcript, video_id)

        try:
            metadata = meta_future.result(timeout=8)
        except Exception:
            logger.warning("Metadata fetch failed for %s, using default", video_id)
            metadata = {"video_title": "YouTube video"}

        try:
            transcript_result = transcript_future.result(timeout=30)
        except TranscriptError as exc:
            transcript_error = exc
        except Exception as exc:
            transcript_error = TranscriptError(str(exc), code="transcript_error")

    if transcript_result is None:
        if not allow_demo_fallback:
            raise transcript_error or TranscriptError("Could not retrieve transcript.")
        demo = demo_transcript_for(video_id, hint)
        # Build a user-friendly reason from the failure chain
        fail_reason = "All transcript sources failed"
        if transcript_error:
            code = getattr(transcript_error, "code", "")
            if code == "no_transcript":
                fail_reason = "This video has no captions/subtitles available (neither manual nor auto-generated)"
            else:
                fail_reason = str(transcript_error.message) if hasattr(transcript_error, "message") else str(transcript_error)
        return {
            "transcript": demo["transcript"],
            "language": "simulated",
            "is_demo": True,
            "video_title": metadata.get("video_title", "Demo video"),
            "video_url": url,
            "video_id": video_id,
            "message": f"Real transcript unavailable: {fail_reason}. Using simulated demo transcript.",
            "fail_reason": fail_reason,
        }
    return {
        "transcript": transcript_result["transcript"],
        "language": transcript_result.get("language", "en"),
        "is_demo": False,
        "video_title": metadata.get("video_title", "YouTube video"),
        "video_url": url,
        "video_id": video_id,
        "message": "",
        "fail_reason": "",
    }