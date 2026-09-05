# app/services/transcript_service.py
"""Fetch real YouTube transcripts with graceful degradation.

Uses multiple sources in order:
  1. Invidious API (free, works from cloud servers) — fetched in parallel
  2. youtube-transcript-api (works from residential IPs)
  3. Simulated demo transcript (fallback)
"""
from __future__ import annotations

import json
import logging
import re
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
]


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


def fetch_transcript(video_id: str, language_hint: Optional[str] = None) -> dict:
    """Fetch a real transcript. Returns dict(transcript, language, is_demo=False)."""

    # Source 1: Invidious API (works from cloud servers)
    transcript_text = _fetch_via_invidious(video_id)
    if transcript_text:
        return {"transcript": transcript_text, "language": "en", "is_demo": False}

    # Source 2: youtube-transcript-api (may work from residential IPs)
    raw = _fetch_with_api(video_id)
    if raw:
        parts = []
        for segment in raw:
            text = segment.get("text", "") if isinstance(segment, dict) else str(segment)
            if text:
                parts.append(_clean_text(text))
        transcript = " ".join(parts)
        if transcript.strip():
            return {"transcript": transcript, "language": "original", "is_demo": False}

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
            transcript_result = transcript_future.result(timeout=15)
        except TranscriptError as exc:
            transcript_error = exc
        except Exception as exc:
            transcript_error = TranscriptError(str(exc), code="transcript_error")

    if transcript_result is None:
        if not allow_demo_fallback:
            raise transcript_error or TranscriptError("Could not retrieve transcript.")
        demo = demo_transcript_for(video_id, hint)
        return {
            "transcript": demo["transcript"],
            "language": "simulated",
            "is_demo": True,
            "video_title": metadata.get("video_title", "Demo video"),
            "video_url": url,
            "video_id": video_id,
            "message": "Real transcript unavailable — using a simulated demo transcript.",
        }
    return {
        "transcript": transcript_result["transcript"],
        "language": transcript_result["language"],
        "is_demo": False,
        "video_title": metadata.get("video_title", "YouTube video"),
        "video_url": url,
        "video_id": video_id,
        "message": "",
    }