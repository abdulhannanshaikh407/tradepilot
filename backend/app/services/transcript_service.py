# app/services/transcript_service.py
"""Fetch real YouTube transcripts with graceful degradation.

Network failures, unavailable captions, private videos and unsupported languages
are converted into typed errors; a deterministic simulated transcript is offered
as the demo fallback.
"""
from __future__ import annotations

import re
from typing import Dict, Optional

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


def _fetch_with_api(video_id: str) -> Optional[list]:
    from youtube_transcript_api import YouTubeTranscriptApi

    if hasattr(YouTubeTranscriptApi, "fetch"):
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
        if hasattr(transcript, "to_raw_data"):
            return transcript.to_raw_data()
        return transcript
    captions = YouTubeTranscriptApi().list(video_id)
    return captions.find_generated_transcript().fetch()


def fetch_transcript(video_id: str, language_hint: Optional[str] = None) -> dict:
    """Fetch a real transcript. Returns dict(transcript, language, is_demo=False)."""
    errors = []
    try:
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
    except Exception as exc:  # noqa: BLE001 — surface every failure as typed error
        errors.append(str(exc))

    # Preferred language fallback via explicit language parameter.
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

        if hasattr(YouTubeTranscriptApi, "fetch"):
            api = YouTubeTranscriptApi()
            requests = api.list(video_id)
        else:
            requests = YouTubeTranscriptApi().list(video_id)
        for transcript in requests:
            if transcript.is_translatable:
                try:
                    translated = transcript.translate("en")
                    data = translated.fetch() if hasattr(translated, "fetch") else translated.fetch()
                    parts = [seg.get("text", "") for seg in data if isinstance(seg, dict) and seg.get("text")]
                    text = _clean_text(" ".join(parts))
                    if text:
                        return {"transcript": text, "language": "en", "is_demo": False}
                except Exception:
                    continue
    except (TranscriptsDisabled, NoTranscriptFound, Exception) as exc:  # noqa: BLE001
        errors.append(str(exc))

    detail = ""
    for err in errors:
        lower = str(err).lower()
        if "disabled" in lower or "subtitles" in lower:
            detail = "Transcripts are disabled for this video."
        elif "private" in lower:
            detail = "This video is private."
        elif "unavailable" in lower:
            detail = "This video is unavailable."
        elif "not found" in lower or "no transcript" in lower:
            detail = "No transcript available for this video."
    raise TranscriptError(
        detail or "Could not retrieve a transcript for this video.",
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