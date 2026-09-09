"""WebSocket test client for TradePilot AI.

Connects to the live WebSocket endpoint, authenticates as the demo user,
listens for signal events, and reports what it receives.

Usage:
    python ws_test_client.py
"""
import asyncio
import json
import sys
import time
import requests
import websockets

BACKEND = "https://tradepilot-xfk2.onrender.com"
WS_URL = "wss://tradepilot-xfk2.onrender.com/ws/signals"
TIMEOUT_SECONDS = 120


def get_demo_token():
    resp = requests.post(f"{BACKEND}/auth/demo", json={}, timeout=60)
    resp.raise_for_status()
    return resp.json()["access_token"]


async def listen_for_signals(token: str):
    received_messages = []
    ws_url = f"{WS_URL}?token={token}"

    print(f"Connecting to {WS_URL}...")
    async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
        print("WebSocket connected!")
        start = time.time()

        while time.time() - start < TIMEOUT_SECONDS:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)
                received_messages.append(data)
                print(f"\n>>> RECEIVED MESSAGE #{len(received_messages)}:")
                print(json.dumps(data, indent=2))
                if data.get("type") == "new_signal":
                    print("\n*** GOT A NEW SIGNAL EVENT ***")
            except asyncio.TimeoutError:
                # No message in 15s — send ping to keep alive
                try:
                    await ws.send("ping")
                except Exception:
                    break
            except websockets.ConnectionClosed:
                print("WebSocket closed by server")
                break

    return received_messages


def force_signal(token):
    resp = requests.post(
        f"{BACKEND}/internal/force-signal",
        json={"symbol": "EUR/USD", "timeframe": "4H"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


async def main():
    token = get_demo_token()
    print(f"Demo token: {token[:20]}...")

    # Start listening in background, fire signal after 3s
    async def listen_task():
        return await listen_for_signals(token)

    async def fire_task():
        await asyncio.sleep(3)
        print("\n--- Firing force-signal endpoint ---")
        result = force_signal(token)
        print(f"Signal created: {result.get('signal_created')}")
        print(f"Signal ID: {result.get('signal', {}).get('signal_id')}")
        return result

    listen_coro = asyncio.ensure_future(listen_task())
    fire_coro = asyncio.ensure_future(fire_task())

    fire_result = await fire_coro
    messages = await listen_coro

    print("\n\n=== SUMMARY ===")
    print(f"Force-signal result: signal_id={fire_result.get('signal', {}).get('signal_id')}")
    print(f"WebSocket messages received: {len(messages)}")
    for i, msg in enumerate(messages):
        print(f"  Message {i+1}: type={msg.get('type')} keys={list(msg.keys())}")
        if msg.get("type") == "new_signal":
            sig = msg.get("signal", {})
            print(f"    signal_id={sig.get('id')} symbol={sig.get('symbol')} source={sig.get('source')}")

    if not any(m.get("type") == "new_signal" for m in messages):
        print("\n*** NO new_signal EVENT RECEIVED — WebSocket delivery may be broken ***")
        sys.exit(1)
    else:
        print("\n*** WebSocket delivery CONFIRMED ***")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
