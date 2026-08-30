# app/api/routes/youtube.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db import models
from app.db.schemas import StrategyOut, YouTubeAnalysisResponse, YouTubeAnalyzeRequest
from app.services import ai_strategy_service, usage_service
from app.services.notification_service import create_notification
from app.services.transcript_service import get_transcript, TranscriptError
from app.services.youtube_service import extract_video_id, is_valid_youtube_url

router = APIRouter(prefix="/youtube", tags=["youtube"])

TRANSCRIPT_HINTS = {
    "RSI Momentum Reversal": "rsi",
    "Golden Cross Trend": "moving average",
    "Momentum Breakout": "breakout",
    "MACD Trend Continuation": "macd",
}


def _save_strategy(db: Session, user: models.User, extracted: dict, url: str | None) -> models.Strategy:
    strategy = models.Strategy(
        user_id=user.id,
        name=extracted["strategy_name"],
        description=extracted.get("description"),
        asset=extracted["asset"],
        market=extracted.get("market"),
        timeframe=extracted["timeframe"],
        strategy_type=extracted.get("strategy_type"),
        direction=extracted["direction"],
        indicators=extracted.get("indicators", []),
        entry_rules=extracted.get("entry_rules", []),
        confirmation_rules=extracted.get("confirmation_rules", []),
        exit_rules=extracted.get("exit_rules", []),
        stop_loss_type=extracted.get("stop_loss_type"),
        stop_loss_value=extracted.get("stop_loss_value"),
        take_profit_type=extracted.get("take_profit_type"),
        take_profit_value=extracted.get("take_profit_value"),
        risk_per_trade=extracted.get("risk_per_trade"),
        risk_reward=extracted.get("risk_reward"),
        confidence=extracted.get("confidence"),
        assumptions=extracted.get("assumptions", []),
        missing_information=extracted.get("missing_information", []),
        source=extracted.get("source", "youtube"),
        source_url=url,
        is_demo=extracted.get("is_demo", False),
    )
    db.add(strategy)
    db.flush()
    return strategy


@router.post("/analyze", response_model=YouTubeAnalysisResponse)
def analyze_youtube(
    payload: YouTubeAnalyzeRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed, _ = usage_service.check_and_increment(db, user, "analyses")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Monthly analysis limit reached for your plan. Upgrade to continue.",
        )

    if not is_valid_youtube_url(payload.url):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL. Please provide a valid video link.")

    video_id = extract_video_id(payload.url)
    if video_id is None:
        raise HTTPException(status_code=400, detail="Could not extract a video ID from that URL.")

    hint = None
    if payload.transcript_override:
        hint = payload.transcript_override

    try:
        transcript_data = get_transcript(video_id, payload.url, allow_demo_fallback=True, hint=hint)
    except TranscriptError as exc:
        raise HTTPException(status_code=422, detail=exc.message)

    transcript = transcript_data["transcript"]
    is_demo = transcript_data.get("is_demo", False)

    extracted = ai_strategy_service.analyze_trading_strategy(transcript)

    strategy = _save_strategy(db, user, extracted, payload.url)
    db.add(
        models.Transcript(
            user_id=user.id,
            strategy_id=strategy.id,
            video_id=video_id,
            video_url=payload.url,
            video_title=transcript_data.get("video_title"),
            language=transcript_data.get("language"),
            transcript_text=transcript,
        )
    )
    db.commit()
    db.refresh(strategy)

    create_notification(
        db,
        user.id,
        "strategy_analyzed",
        "Strategy analyzed",
        f"'{strategy.name}' was extracted from your video and saved.",
        user.email,
    )

    return YouTubeAnalysisResponse(
        strategy=StrategyOut.model_validate(strategy),
        transcript_preview=transcript[:400],
        video_id=video_id,
        video_title=transcript_data.get("video_title"),
        used_demo_fallback=is_demo,
        message=(
            transcript_data.get("message", "")
            if is_demo
            else "Strategy extracted successfully."
        ),
    )


@router.get("/demo-strategies")
def demo_strategies():
    """Deterministic demo strategies shown in the analyzer UI."""
    return {"strategies": ai_strategy_service.available_demo_strategies()}