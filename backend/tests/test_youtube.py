from conftest import auth

from app.api.routes import youtube as youtube_route

DEMO_TRANSCRIPT = (
    "In this video I break down my RSI momentum reversal strategy on Bitcoin. "
    "We trade the 4 hour chart and this strategy is long only. First we wait for "
    "the RSI 14 to drop below 30, an oversold condition, then we wait for it to "
    "cross back above 30 as our entry trigger. Price must stay above the 200 EMA "
    "as confirmation. Our stop loss is 2% below entry and our take profit is 4% "
    "giving us a 1 to 2 risk reward. We risk 1% of our account per trade. "
    "If price closes below the 200 EMA we exit early."
)


def _signup(client, email="youtube@test.dev"):
    response = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "name": "YouTube Tester"},
    )
    return response.json()["access_token"]


def _fake_get_transcript(video_id, url, allow_demo_fallback=True, hint=None):
    return {
        "transcript": DEMO_TRANSCRIPT,
        "language": "simulated",
        "is_demo": True,
        "video_title": "RSI Momentum Reversal",
        "video_url": url,
        "video_id": video_id,
        "message": "Real transcript unavailable — using a simulated demo transcript.",
    }


def test_demo_strategies_endpoint(client):
    response = client.get("/youtube/demo-strategies")
    assert response.status_code == 200
    strategies = response.json()["strategies"]
    assert len(strategies) >= 3
    for s in strategies:
        assert s["strategy_name"]
        assert s["entry_rules"]


def test_analyze_rejects_invalid_url(client):
    token = _signup(client, "badurl@test.dev")
    response = client.post(
        "/youtube/analyze",
        json={"url": "not-a-youtube-url"},
        headers=auth(token),
    )
    assert response.status_code == 400


def test_analyze_with_demo_fallback(client, monkeypatch):
    token = _signup(client, "demo@test.dev")
    monkeypatch.setattr(youtube_route, "get_transcript", _fake_get_transcript)

    response = client.post(
        "/youtube/analyze",
        json={"url": "https://www.youtube.com/watch?v=abcDEFghijk"},
        headers=auth(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["used_demo_fallback"] is True
    assert body["video_id"] == "abcDEFghijk"
    strategy = body["strategy"]
    assert strategy["name"]
    assert strategy["direction"] in ("LONG", "SHORT")
    assert strategy["entry_rules"]
    assert strategy["is_demo"]

    saved = client.get("/strategies", headers=auth(token)).json()
    assert any(s["name"] == strategy["name"] for s in saved)


def test_analyze_requires_auth(client):
    response = client.post(
        "/youtube/analyze",
        json={"url": "https://www.youtube.com/watch?v=abcDEFghijk"},
    )
    assert response.status_code == 401