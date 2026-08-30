# app/services/indicators.py
"""Pure-Python technical indicators used by the backtest and signal engines.

All functions are vectorised over lists and are deterministic (no external deps).
"""
from __future__ import annotations

from typing import List, Tuple


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        return out
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or not values:
        return out
    k = 2.0 / (period + 1.0)
    prev = values[0]
    out[0] = prev
    for i in range(1, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1 + avg_gain / avg_loss))

    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1 + avg_gain / avg_loss))
    return out


def macd(
    values: list[float], fast: int = 12, slow: int = 26, signal_period: int = 9
) -> Tuple[list[float | None], list[float | None], list[float | None]]:
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    macd_line: list[float | None] = []
    for i in range(len(values)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line.append(ema_fast[i] - ema_slow[i])
        else:
            macd_line.append(None)
    # Signal line = EMA of the MACD (ignore None seed)
    clean: list[float] = [m for m in macd_line if m is not None]
    if not clean:
        return macd_line, [None] * len(values), [None] * len(values)
    k = 2.0 / (signal_period + 1.0)
    signal_line: list[float | None] = [None] * len(values)
    first_idx = next(i for i, m in enumerate(macd_line) if m is not None)
    prev = macd_line[first_idx]
    signal_line[first_idx] = prev
    for i in range(first_idx + 1, len(values)):
        if macd_line[i] is None:
            continue
        prev = macd_line[i] * k + prev * (1 - k)
        signal_line[i] = prev
    histogram = [
        (macd_line[i] - signal_line[i]) if macd_line[i] is not None and signal_line[i] is not None else None
        for i in range(len(values))
    ]
    return macd_line, signal_line, histogram


def highest(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(len(values)):
        start = max(0, i - period + 1)
        window = values[start : i + 1]
        if window:
            out[i] = max(window)
    return out


def lowest(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(len(values)):
        start = max(0, i - period + 1)
        window = values[start : i + 1]
        if window:
            out[i] = min(window)
    return out


def crossover(a: list[float | None], b: list[float | None]) -> list[bool]:
    out: list[bool] = [False] * len(a)
    for i in range(1, len(a)):
        if (
            a[i] is not None
            and b[i] is not None
            and a[i - 1] is not None
            and b[i - 1] is not None
        ):
            if a[i - 1] <= b[i - 1] and a[i] > b[i]:
                out[i] = True
    return out


def crossbelow(a: list[float | None], b: list[float | None]) -> list[bool]:
    out: list[bool] = [False] * len(a)
    for i in range(1, len(a)):
        if (
            a[i] is not None
            and b[i] is not None
            and a[i - 1] is not None
            and b[i - 1] is not None
        ):
            if a[i - 1] >= b[i - 1] and a[i] < b[i]:
                out[i] = True
    return out


def cross_above_value(a: list[float | None], value: float) -> list[bool]:
    out: list[bool] = [False] * len(a)
    for i in range(1, len(a)):
        if a[i] is not None and a[i - 1] is not None:
            if a[i - 1] <= value < a[i]:
                out[i] = True
    return out


def cross_below_value(a: list[float | None], value: float) -> list[bool]:
    out: list[bool] = [False] * len(a)
    for i in range(1, len(a)):
        if a[i] is not None and a[i - 1] is not None:
            if a[i - 1] >= value > a[i]:
                out[i] = True
    return out