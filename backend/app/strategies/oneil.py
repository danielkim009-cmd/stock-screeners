"""
O'Neil CAN SLIM Pattern Screener
---------------------------------
Detects five classic William O'Neil base patterns:

  1. Cup-with-Handle (CUP_HANDLE): 7–52 week U-shaped consolidation with a
     short handle on the right side. Pivot = high of the handle.

  2. Flat Base (FLAT_BASE): 5+ week sideways consolidation with ≤15%
     correction from the high. Typically follows a prior breakout.
     Pivot = high of the base.

  3. Double Bottom (DOUBLE_BOTTOM): "W" pattern where the second low
     undercuts the first.  The middle peak of the "W" is the buy point.
     Pivot = middle peak high.

  4. Saucer (SAUCER): 12 weeks–2 year gradual rounding base with a flat,
     extended bottom and a shallow 12–35% correction.  Optional handle on
     the right side.  Distinguishable from a cup by the high proportion of
     bars that cluster near the base low.  Pivot = high of the handle (or
     right lip when no handle is present).

  5. Ascending Base (ASCENDING_BASE): 9–16 week staircase of 3 waves,
     each with a higher high and higher low than the prior wave.  Each
     pullback corrects 10–20%.  Pivot = high of the 3rd (rightmost) wave.

A breakout is confirmed when the close exceeds the pivot on volume that
is at least 40% above the 50-day average volume.

All pattern windows use *prior* bar data only — no look-ahead.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal

import numpy as np
import pandas as pd

PatternType = Literal["CUP_HANDLE", "FLAT_BASE", "DOUBLE_BOTTOM", "SAUCER", "ASCENDING_BASE"]


# --------------------------------------------------------------------------- #
#  Signal dataclass
# --------------------------------------------------------------------------- #

@dataclass
class OneilSignal:
    ticker:        str
    pattern:       str        # "CUP_HANDLE" | "FLAT_BASE" | "DOUBLE_BOTTOM"
    pivot:         float      # the buy point / pivot price
    last_close:    float
    breakout:      bool       # close > pivot
    breakout_vol:  bool       # volume ≥ 40% above 50d avg
    rel_volume:    float      # today vol / 50d avg vol
    depth_pct:     float      # cup or base correction depth (%)
    base_weeks:    int        # length of the base in weeks
    pct_from_pivot: float     # (close - pivot) / pivot * 100


# --------------------------------------------------------------------------- #
#  Internal helpers
# --------------------------------------------------------------------------- #

def _avg_vol(volume: np.ndarray, period: int = 50) -> float:
    """50-day average volume excluding today."""
    n = len(volume)
    if n < 2:
        return float(volume[-1]) if n == 1 else 0.0
    end = n - 1
    start = max(0, end - period)
    return float(volume[start:end].mean())


def _detect_cup_handle(
    close: np.ndarray,
    high:  np.ndarray,
    volume: np.ndarray,
) -> Optional[dict]:
    """
    Scan for cup-with-handle.  Tries cup lengths from 35 to 200 bars,
    returns the shortest (most recent) valid pattern found.
    """
    n = len(close)

    for cup_len in range(35, min(201, n - 4)):
        handle_len = max(5, min(25, cup_len // 7))
        total = cup_len + handle_len
        if total + 1 > n:
            break

        cup_c  = close[-(total): -(handle_len)]
        hdl_c  = close[-(handle_len):]
        hdl_h  = high[-(handle_len):]
        lc     = len(cup_c)

        if lc < 10:
            continue

        # Left lip: max of first third
        split  = max(1, lc // 3)
        left_high = float(cup_c[:split].max())

        # Cup low: min of middle half
        mid_s  = max(1, lc // 4)
        mid_e  = max(mid_s + 1, 3 * lc // 4)
        cup_low = float(cup_c[mid_s:mid_e].min())

        # Right lip: max of last third
        right_high = float(cup_c[2 * split:].max()) if len(cup_c[2 * split:]) > 0 else left_high

        # ── Cup conditions ──────────────────────────────────────────────── #
        if left_high <= 0:
            continue
        depth = (left_high - cup_low) / left_high
        if not (0.12 <= depth <= 0.40):          # 12–40% correction (O'Neil typical range)
            continue
        if right_high < left_high * 0.90:        # right lip ≥ 90% of left (tightened from 0.85)
            continue

        # Prior uptrend: price 21 bars before the cup must be meaningfully below
        # the left lip — confirms the cup formed after a rally, not a downtrend
        pre_cup_idx = n - total - 21
        if pre_cup_idx >= 0:
            if float(close[pre_cup_idx]) >= left_high * 0.85:
                continue    # no meaningful prior advance into the left lip

        # Roundedness: avoid V-shapes — at least 10% of middle bars should
        # be within 8% of the cup low (stock spent time consolidating at bottom)
        mid_bars = cup_c[mid_s:mid_e]
        near_low = int(np.sum(mid_bars <= cup_low * 1.08))
        if near_low / len(mid_bars) < 0.10:
            continue

        # Recovery confirmation: the end of the cup (before the handle starts)
        # must be near the right lip — confirms the stock has actually recovered
        cup_end = float(cup_c[-5:].max()) if lc >= 5 else float(cup_c[-1])
        if cup_end < right_high * 0.88:
            continue

        # ── Handle conditions ────────────────────────────────────────────── #
        handle_min   = float(hdl_c.min())
        handle_corr  = (right_high - handle_min) / right_high if right_high > 0 else 1.0
        if handle_corr > 0.15:                   # handle corrects ≤ 15%
            continue

        cup_midpoint = cup_low + (left_high - cup_low) * 0.5
        if handle_min < cup_midpoint:             # handle stays in upper half
            continue

        pivot = float(hdl_h.max())
        return {
            "pattern":    "CUP_HANDLE",
            "pivot":      round(pivot, 2),
            "depth_pct":  round(depth * 100, 1),
            "base_weeks": round(cup_len / 5),
        }

    return None


def _detect_flat_base(
    close: np.ndarray,
    high:  np.ndarray,
) -> Optional[dict]:
    """
    Detect a flat base: 5–16 week tight sideways action (≤15% correction).
    The base must be forming near the stock's recent highs (not just any drift).
    """
    n = len(close)

    for base_len in range(25, min(81, n - 1)):
        base_c = close[-(base_len + 1):-1]   # exclude current bar
        base_h = high[-(base_len + 1):-1]

        base_high = float(base_c.max())
        base_low  = float(base_c.min())
        if base_high <= 0:
            continue

        correction = (base_high - base_low) / base_high
        if correction > 0.15:
            continue     # too wide — not a flat base

        # The base high must be near the stock's 52-week high (within 20%)
        lookback_high = float(high[-min(252, n):].max())
        if base_high < lookback_high * 0.80:
            continue     # base is not near highs — likely a downtrend channel

        pivot = round(float(base_h.max()), 2)
        return {
            "pattern":    "FLAT_BASE",
            "pivot":      pivot,
            "depth_pct":  round(correction * 100, 1),
            "base_weeks": round(base_len / 5),
        }

    return None


def _detect_double_bottom(
    close: np.ndarray,
    high:  np.ndarray,
) -> Optional[dict]:
    """
    Detect a double-bottom "W" pattern.

    Approach:
      - Scan 35–150 bar windows for a W shape.
      - The window is split into 5 sections; we look for
        high → low1 → mid-peak → low2 (≤ low1) → recovery.
      - Pivot = mid-peak high.
    """
    n = len(close)

    for base_len in range(35, min(151, n - 1)):
        seg = close[-(base_len + 1):-1]
        seg_high = high[-(base_len + 1):-1]
        m = len(seg)

        if m < 20:
            continue

        # Divide into 5 rough equal sections
        s = m // 5

        # Left peak (entry of pattern)
        left_peak = float(seg[:s].max())

        # First low
        low1_arr   = seg[s: 2 * s]
        low1       = float(low1_arr.min())
        low1_idx   = int(low1_arr.argmin()) + s

        # Middle peak (between the two lows)
        mid_arr    = seg[2 * s: 3 * s]
        mid_peak_c = float(mid_arr.max())
        mid_peak_h = float(seg_high[2 * s: 3 * s].max())

        # Second low
        low2_arr   = seg[3 * s: 4 * s]
        low2       = float(low2_arr.min())

        # Right side recovery
        recovery   = float(seg[4 * s:].max())

        # ── W shape conditions ────────────────────────────────────────────── #
        # Second low must undercut the first
        if low2 >= low1:
            continue

        # Middle peak below the left peak (not at new high)
        if mid_peak_c >= left_peak:
            continue

        # Both lows must be meaningfully below the left peak (at least 10%)
        if left_peak <= 0:
            continue
        depth1 = (left_peak - low1) / left_peak
        depth2 = (left_peak - low2) / left_peak
        if depth1 < 0.10 or depth2 < 0.10:
            continue
        if depth1 > 0.45 or depth2 > 0.45:
            continue

        # Recovery on right side should clear the mid peak
        if recovery < mid_peak_c * 0.95:
            continue

        # Mid peak is the pivot
        pivot = round(float(mid_peak_h), 2)
        depth = round(max(depth1, depth2) * 100, 1)

        return {
            "pattern":    "DOUBLE_BOTTOM",
            "pivot":      pivot,
            "depth_pct":  depth,
            "base_weeks": round(base_len / 5),
        }

    return None


def _detect_saucer(
    close:  np.ndarray,
    high:   np.ndarray,
    volume: np.ndarray,
) -> Optional[dict]:
    """
    Detect a saucer (with optional handle).

    Like a cup-with-handle but with a longer duration and a distinctively
    flat, extended bottom where the stock consolidates near its low for many
    weeks before recovering.

    Criteria:
      • Duration: 60–260 bars (12 weeks – ~1 year).
      • Depth (left high → saucer low): 12–35%.
      • Right lip ≥ 85% of left lip.
      • Flatness: ≥ 25% of bars in the middle half are within 5% of the
        base low — this distinguishes a saucer from a cup.
      • Handle (optional): ≤ 15% correction; stays in upper half of base.

    Pivot = high of the handle (or right lip when no handle is present).
    """
    n = len(close)

    for saucer_len in range(60, min(261, n - 4)):
        handle_len = max(5, min(25, saucer_len // 10))
        total = saucer_len + handle_len
        if total + 1 > n:
            break

        saucer_c = close[-(total):-(handle_len)]
        hdl_c    = close[-(handle_len):]
        hdl_h    = high[-(handle_len):]
        lc       = len(saucer_c)

        if lc < 40:
            continue

        # Left lip: max of first quarter
        q          = max(1, lc // 4)
        left_high  = float(saucer_c[:q].max())

        # Saucer low: min of middle half
        mid_s      = max(1, lc // 4)
        mid_e      = max(mid_s + 1, 3 * lc // 4)
        saucer_low = float(saucer_c[mid_s:mid_e].min())

        # Right lip: max of last quarter
        right_high = float(saucer_c[3 * q:].max()) if len(saucer_c[3 * q:]) > 0 else left_high

        if left_high <= 0:
            continue

        depth = (left_high - saucer_low) / left_high
        if not (0.12 <= depth <= 0.35):
            continue

        if right_high < left_high * 0.85:
            continue

        # Flatness test: middle half must have many bars near the base low.
        # This is the key feature that separates a saucer from a cup.
        mid_bars        = saucer_c[mid_s:mid_e]
        near_low_count  = int(np.sum(mid_bars <= saucer_low * 1.05))
        flatness_ratio  = near_low_count / len(mid_bars)
        if flatness_ratio < 0.25:
            continue

        # Handle (required to exist and be well-formed)
        handle_min  = float(hdl_c.min())
        handle_corr = (right_high - handle_min) / right_high if right_high > 0 else 1.0
        if handle_corr > 0.15:
            continue

        saucer_midpoint = saucer_low + (left_high - saucer_low) * 0.5
        if handle_min < saucer_midpoint:
            continue

        pivot = round(float(hdl_h.max()), 2)
        return {
            "pattern":    "SAUCER",
            "pivot":      pivot,
            "depth_pct":  round(depth * 100, 1),
            "base_weeks": round(saucer_len / 5),
        }

    return None


def _detect_ascending_base(
    close:  np.ndarray,
    high:   np.ndarray,
    low:    np.ndarray,
) -> Optional[dict]:
    """
    Detect an ascending base: 9–16 week staircase pattern.

    The base is divided into 3 roughly equal sections.  Valid when:
      • Each section's low is higher than the previous section's low.
      • Each section's high is higher than the previous section's high.
      • Each intra-section pullback (high→low) is 10–20%.
      • The rightmost section high is within 25% of the 52-week high.
      • There is a prior uptrend leading into the base.

    Pivot = high of the 3rd (rightmost) section.
    """
    n = len(close)

    for base_len in range(45, min(81, n - 1)):
        seg_h = high[-(base_len + 1):-1]   # exclude current bar
        seg_l = low[-(base_len + 1):-1]
        m = len(seg_h)

        if m < 30:
            continue

        s = m // 3

        # Section highs and lows (use actual high/low arrays)
        hi = [float(seg_h[i * s:(i + 1) * s].max()) for i in range(3)]
        lo = [float(seg_l[i * s:(i + 1) * s].min()) for i in range(3)]

        # Ascending: each section's high AND low must exceed the previous
        if not (lo[0] < lo[1] < lo[2]):
            continue
        if not (hi[0] < hi[1] < hi[2]):
            continue

        # Each section must have a 10–20% intra-pullback (high → low)
        depths = []
        valid = True
        for h_i, l_i in zip(hi, lo):
            if h_i <= 0:
                valid = False
                break
            d = (h_i - l_i) / h_i
            if not (0.10 <= d <= 0.20):
                valid = False
                break
            depths.append(d)
        if not valid:
            continue

        # Must be forming near the 52-week high (no downtrend masquerade)
        lookback_high = float(high[-min(252, n):].max())
        if hi[2] < lookback_high * 0.75:
            continue

        # Prior uptrend: the close ~1 month before the base should be below
        # the base's entry high, confirming we are consolidating a rally.
        lookback_idx = max(0, n - base_len - 21)
        pre_close = float(close[lookback_idx])
        if pre_close >= hi[0] * 0.95:
            continue   # no meaningful rally preceding the base

        avg_depth = round(sum(depths) / len(depths) * 100, 1)
        pivot = round(float(seg_h[2 * s:].max()), 2)

        return {
            "pattern":    "ASCENDING_BASE",
            "pivot":      pivot,
            "depth_pct":  avg_depth,
            "base_weeks": round(base_len / 5),
        }

    return None


# --------------------------------------------------------------------------- #
#  Public screener function
# --------------------------------------------------------------------------- #

PATTERN_PRIORITY = {"CUP_HANDLE": 0, "FLAT_BASE": 1, "DOUBLE_BOTTOM": 2, "SAUCER": 3, "ASCENDING_BASE": 4}


def screen_oneil(df: pd.DataFrame, ticker: str) -> Optional[OneilSignal]:
    """
    Detect the highest-priority O'Neil pattern in the OHLCV data.

    Priority order (most significant first):
      1. Cup-with-Handle
      2. Flat Base
      3. Double Bottom
      4. Saucer
      5. Ascending Base

    Returns OneilSignal if any pattern is detected, else None.
    Requires at least 60 bars of data.
    """
    if len(df) < 60:
        return None

    close  = df["Close"].values.astype(float)
    high   = df["High"].values.astype(float)
    low    = df["Low"].values.astype(float)
    volume = df["Volume"].values.astype(float)

    last_close = float(close[-1])
    avg_vol    = _avg_vol(volume)
    rel_vol    = float(volume[-1]) / avg_vol if avg_vol > 0 else 0.0

    # Try patterns in priority order
    result = (
        _detect_cup_handle(close, high, volume)
        or _detect_flat_base(close, high)
        or _detect_double_bottom(close, high)
        or _detect_saucer(close, high, volume)
        or _detect_ascending_base(close, high, low)
    )

    if result is None:
        return None

    pivot         = result["pivot"]
    breakout      = last_close > pivot
    breakout_vol  = rel_vol >= 1.4
    pct_from_pivot = (last_close - pivot) / pivot * 100 if pivot > 0 else 0.0

    # Ignore if price is already more than 5% past the pivot (extended)
    if pct_from_pivot > 5.0:
        return None

    return OneilSignal(
        ticker=ticker,
        pattern=result["pattern"],
        pivot=pivot,
        last_close=round(last_close, 2),
        breakout=breakout,
        breakout_vol=breakout_vol and breakout,
        rel_volume=round(rel_vol, 2),
        depth_pct=result["depth_pct"],
        base_weeks=result["base_weeks"],
        pct_from_pivot=round(pct_from_pivot, 1),
    )
