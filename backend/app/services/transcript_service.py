# app/services/transcript_service.py
"""Fetch real YouTube transcripts with graceful degradation.

Uses multiple sources in order:
  1. Invidious API (free, works from cloud servers)
  2. youtube-transcript-api (works from residential IPs)
  3. Simulated demo transcript (fallback)
"""
from __future__ import annotations

import json
import re
from typing import Dict, Optional

import httpx

from app.services.youtube_service import SAMPLE_TRANSCRIPTS, demo_transcript_for, fetch_video_metadata


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


# Free Invidious instances that work from cloud servers
INVIDIOUS_INSTANCES = [
    "https://vid.puffyan.us",
    "https://inv.nadeko.net",
    "https://invidious.snopyta.org",
    "https://yewtu.be",
    "https://invidious.kavin.rocks",
    "https://iv.ggtyler.dev",
]


def _fetch_via_invidious(video_id: str) -> Optional[str]:
    """Fetch transcript via free Invidious API instances."""
    for instance in INVIDIOUS_INSTANCES:
        try:
            # Get captions list
            url = f"{instance}/api/v1/captions/{video_id}"
            resp = httpx.get(url, timeout=10, follow_redirects=True)
            if resp.status_code != 200:
                continue

            captions = resp.json()
            if not captions or not isinstance(captions, list):
                continue

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
                continue

            # Fetch the actual transcript
            if caption_url.startswith("/"):
                caption_url = f"{instance}{caption_url}"

            # Request JSON format if possible
            if "?" in caption_url:
                caption_url += "&fmt=json3"
            else:
                caption_url += "?fmt=json3"

            t_resp = httpx.get(caption_url, timeout=10, follow_redirects=True)
            if t_resp.status_code != 200:
                # Try without fmt parameter
                clean_url = caption_url.split("?")[0]
                t_resp = httpx.get(clean_url, timeout=10, follow_redirects=True)
                if t_resp.status_code != 200:
                    continue

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
            # Remove XML/HTML tags
            clean = re.sub(r"<[^>]+>", " ", text)
            clean = re.sub(r"&amp;", "&", clean)
            clean = re.sub(r"&#39;", "'", clean)
            clean = re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}", "", clean)
            clean = re.sub(r"\d+\s*$", "", clean, flags=re.MULTILINE)
            clean = re.sub(r"\s+", " ", clean).strip()
            if len(clean) > 50:
                return _clean_text(clean)

        except Exception:
            continue

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
    metadata = fetch_video_metadata(video_id)
    try:
        result = fetch_transcript(video_id)
    except TranscriptError:
        if not allow_demo_fallback:
            raise
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
        "transcript": result["transcript"],
        "language": result["language"],
        "is_demo": False,
        "video_title": metadata.get("video_title", "YouTube video"),
        "video_url": url,
        "video_id": video_id,
        "message": "",
    }