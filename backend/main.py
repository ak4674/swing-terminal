"""
SWING Terminal — FastAPI backend (v2 · yfinance edition)
Fetches live quotes + OHLCV history via yfinance (works from any cloud IP),
computes RSI (Wilder), EMA, MACD, ATR, ADX, volume ratio, trend signal,
and scores each stock 0-100 against 5 swing patterns with improved heuristics.
Cache: 5-min TTL on full universe, 2-min on individual quotes.
"""
import os
import time
import logging
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

import numpy as np
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("swing")

# ─────────────────────────────────────────────────────────────────────────────
# STOCK UNIVERSE  (symbol.NS for yfinance NSE tickers)
# (symbol, display_symbol, company, sector, cap, approx_listing_age_days)
# ─────────────────────────────────────────────────────────────────────────────
UNIVERSE = [
    # ── Information Technology ──────────────────────────────────────────────
    ("TCS.NS",         "TCS",         "Tata Consultancy Services",      "Information Technology",  "large", 5500),
    ("INFY.NS",        "INFY",        "Infosys",                        "Information Technology",  "large", 8000),
    ("WIPRO.NS",       "WIPRO",       "Wipro",                          "Information Technology",  "large", 8000),
    ("HCLTECH.NS",     "HCLTECH",     "HCL Technologies",               "Information Technology",  "large", 7000),
    ("TECHM.NS",       "TECHM",       "Tech Mahindra",                  "Information Technology",  "large", 5500),
    ("LTIM.NS",        "LTIM",        "LTIMindtree",                    "Information Technology",  "mid",   900),
    ("PERSISTENT.NS",  "PERSISTENT",  "Persistent Systems",             "Information Technology",  "mid",   4500),
    ("COFORGE.NS",     "COFORGE",     "Coforge",                        "Information Technology",  "mid",   5000),
    ("KPITTECH.NS",    "KPITTECH",    "KPIT Technologies",              "Information Technology",  "small", 1800),
    ("TATAELXSI.NS",   "TATAELXSI",  "Tata Elxsi",                     "Information Technology",  "mid",   7000),
    ("HAPPSTMNDS.NS",  "HAPPSTMNDS",  "Happiest Minds Technologies",    "Information Technology",  "small", 1500),
    ("LATENTVIEW.NS",  "LATENTVIEW",  "Latent View Analytics",          "Information Technology",  "small", 1400),
    ("MAPMYINDIA.NS",  "MAPMYINDIA",  "C.E. Info Systems",              "Information Technology",  "small", 1100),

    # ── Banking & Financials ─────────────────────────────────────────────────
    ("HDFCBANK.NS",    "HDFCBANK",    "HDFC Bank",                      "Banking & Financials",    "large", 9000),
    ("ICICIBANK.NS",   "ICICIBANK",   "ICICI Bank",                     "Banking & Financials",    "large", 9000),
    ("AXISBANK.NS",    "AXISBANK",    "Axis Bank",                      "Banking & Financials",    "large", 8500),
    ("KOTAKBANK.NS",   "KOTAKBANK",   "Kotak Mahindra Bank",            "Banking & Financials",    "large", 8000),
    ("SBIN.NS",        "SBIN",        "State Bank of India",            "Banking & Financials",    "large", 9000),
    ("BAJFINANCE.NS",  "BAJFINANCE",  "Bajaj Finance",                  "Banking & Financials",    "large", 6000),
    ("BAJAJFINSV.NS",  "BAJAJFINSV",  "Bajaj Finserv",                  "Banking & Financials",    "large", 5500),
    ("CDSL.NS",        "CDSL",        "Central Depository Services",    "Banking & Financials",    "small", 2800),
    ("PAYTM.NS",       "PAYTM",       "One97 Communications",           "Banking & Financials",    "mid",   1550),
    ("BANDHANBNK.NS",  "BANDHANBNK",  "Bandhan Bank",                   "Banking & Financials",    "mid",   2200),
    ("FEDERALBNK.NS",  "FEDERALBNK",  "Federal Bank",                   "Banking & Financials",    "mid",   5000),

    # ── Energy ───────────────────────────────────────────────────────────────
    ("RELIANCE.NS",    "RELIANCE",    "Reliance Industries",            "Energy",                  "large", 9000),
    ("ONGC.NS",        "ONGC",        "ONGC",                           "Energy",                  "large", 8500),
    ("IOC.NS",         "IOC",         "Indian Oil Corporation",         "Energy",                  "large", 8000),
    ("BPCL.NS",        "BPCL",        "Bharat Petroleum",               "Energy",                  "large", 8000),
    ("IEX.NS",         "IEX",         "Indian Energy Exchange",         "Energy",                  "mid",   1500),
    ("ADANIGREEN.NS",  "ADANIGREEN",  "Adani Green Energy",             "Energy",                  "large", 1600),
    ("POWERGRID.NS",   "POWERGRID",   "Power Grid Corporation",         "Energy",                  "large", 5000),

    # ── Pharmaceuticals ──────────────────────────────────────────────────────
    ("SUNPHARMA.NS",   "SUNPHARMA",   "Sun Pharmaceutical",             "Pharmaceuticals",         "large", 8000),
    ("DRREDDY.NS",     "DRREDDY",     "Dr Reddy's Laboratories",        "Pharmaceuticals",         "large", 8500),
    ("CIPLA.NS",       "CIPLA",       "Cipla",                          "Pharmaceuticals",         "large", 8500),
    ("LUPIN.NS",       "LUPIN",       "Lupin",                          "Pharmaceuticals",         "mid",   7500),
    ("MANKIND.NS",     "MANKIND",     "Mankind Pharma",                 "Pharmaceuticals",         "mid",   900),
    ("METROPOLIS.NS",  "METROPOLIS",  "Metropolis Healthcare",          "Pharmaceuticals",         "small", 2500),

    # ── Auto & Ancillaries ───────────────────────────────────────────────────
    ("MARUTI.NS",      "MARUTI",      "Maruti Suzuki India",            "Auto & Ancillaries",      "large", 7500),
    ("M&M.NS",         "M&M",         "Mahindra & Mahindra",            "Auto & Ancillaries",      "large", 8500),
    ("TATAMOTORS.NS",  "TATAMOTORS",  "Tata Motors",                    "Auto & Ancillaries",      "large", 9000),
    ("BAJAJ-AUTO.NS",  "BAJAJ-AUTO",  "Bajaj Auto",                     "Auto & Ancillaries",      "large", 6000),
    ("EICHERMOT.NS",   "EICHERMOT",   "Eicher Motors",                  "Auto & Ancillaries",      "large", 7000),
    ("SONACOMS.NS",    "SONACOMS",    "Sona BLW Precision",             "Auto & Ancillaries",      "mid",   1700),
    ("MOTHERSON.NS",   "MOTHERSON",   "Samvardhana Motherson Intl",     "Auto & Ancillaries",      "large", 6000),

    # ── FMCG ─────────────────────────────────────────────────────────────────
    ("ITC.NS",         "ITC",         "ITC",                            "FMCG",                    "large", 9000),
    ("HINDUNILVR.NS",  "HINDUNILVR",  "Hindustan Unilever",             "FMCG",                    "large", 9000),
    ("NESTLEIND.NS",   "NESTLEIND",   "Nestle India",                   "FMCG",                    "large", 8500),
    ("BRITANNIA.NS",   "BRITANNIA",   "Britannia Industries",           "FMCG",                    "large", 8500),
    ("DABUR.NS",       "DABUR",       "Dabur India",                    "FMCG",                    "large", 8500),
    ("ASIANPAINT.NS",  "ASIANPAINT",  "Asian Paints",                   "FMCG",                    "large", 8500),
    ("MARICO.NS",      "MARICO",      "Marico",                         "FMCG",                    "large", 7000),

    # ── Capital Goods ────────────────────────────────────────────────────────
    ("LT.NS",          "LT",          "Larsen & Toubro",                "Capital Goods",            "large", 8500),
    ("ULTRACEMCO.NS",  "ULTRACEMCO",  "UltraTech Cement",               "Capital Goods",            "large", 7000),
    ("POLYCAB.NS",     "POLYCAB",     "Polycab India",                  "Capital Goods",            "mid",   2300),
    ("ASTRAL.NS",      "ASTRAL",      "Astral Ltd",                     "Capital Goods",            "mid",   5500),
    ("IRCTC.NS",       "IRCTC",       "Indian Railway Catering",        "Capital Goods",            "mid",   2300),
    ("ABB.NS",         "ABB",         "ABB India",                      "Capital Goods",            "large", 7000),

    # ── Metals ───────────────────────────────────────────────────────────────
    ("TATASTEEL.NS",   "TATASTEEL",   "Tata Steel",                     "Metals",                  "large", 9000),
    ("JSWSTEEL.NS",    "JSWSTEEL",    "JSW Steel",                      "Metals",                  "large", 7000),
    ("HINDALCO.NS",    "HINDALCO",    "Hindalco Industries",            "Metals",                  "large", 8000),
    ("SAIL.NS",        "SAIL",        "Steel Authority of India",       "Metals",                  "large", 8500),

    # ── Consumer Durables ────────────────────────────────────────────────────
    ("TITAN.NS",       "TITAN",       "Titan Company",                  "Consumer Durables",       "large", 8000),
    ("VOLTAS.NS",      "VOLTAS",      "Voltas",                         "Consumer Durables",       "mid",   8000),
    ("DIXON.NS",       "DIXON",       "Dixon Technologies",             "Consumer Durables",       "mid",   1900),
    ("NYKAA.NS",       "NYKAA",       "FSN E-Commerce Ventures",        "Consumer Durables",       "mid",   1550),
    ("ZOMATO.NS",      "ZOMATO",      "Zomato",                         "Consumer Durables",       "mid",   1700),
    ("TRENT.NS",       "TRENT",       "Trent",                          "Consumer Durables",       "mid",   8000),

    # ── Chemicals ────────────────────────────────────────────────────────────
    ("PIIND.NS",       "PIIND",       "PI Industries",                  "Chemicals",               "mid",   6000),
    ("SRF.NS",         "SRF",         "SRF",                            "Chemicals",               "mid",   7000),
    ("DEEPAKNTR.NS",   "DEEPAKNTR",   "Deepak Nitrite",                 "Chemicals",               "mid",   6000),
    ("NAVINFLUOR.NS",  "NAVINFLUOR",  "Navin Fluorine",                 "Chemicals",               "mid",   7000),
    ("AAPL",           "AAPL",        "Placeholder (remove)",           "Chemicals",               "mid",   7000),  # will be skipped gracefully
]

# Remove placeholder
UNIVERSE = [u for u in UNIVERSE if u[0] != "AAPL"]


# ─────────────────────────────────────────────────────────────────────────────
# INDICATORS  (vectorised, Wilder smoothing where standard)
# ─────────────────────────────────────────────────────────────────────────────

def _arr(closes: List[float]) -> np.ndarray:
    return np.array(closes, dtype=np.float64)


def rsi_wilder(closes: List[float], period: int = 14) -> Optional[float]:
    """Wilder RSI — the standard used by TradingView, Bloomberg."""
    arr = _arr(closes)
    if len(arr) < period + 1:
        return None
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    # Seed with SMA
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def ema_series(closes: List[float], period: int) -> Optional[np.ndarray]:
    arr = _arr(closes)
    if len(arr) < period:
        return None
    k = 2.0 / (period + 1)
    result = np.empty(len(arr))
    result[:] = np.nan
    result[period - 1] = arr[:period].mean()
    for i in range(period, len(arr)):
        result[i] = arr[i] * k + result[i - 1] * (1 - k)
    return result


def ema_val(closes: List[float], period: int) -> Optional[float]:
    s = ema_series(closes, period)
    if s is None:
        return None
    vals = s[~np.isnan(s)]
    return float(vals[-1]) if len(vals) else None


def macd_signal(closes: List[float]) -> Tuple[Optional[float], Optional[float]]:
    """Returns (MACD line, Signal line). Positive MACD → bullish momentum."""
    if len(closes) < 35:
        return None, None
    fast = ema_series(closes, 12)
    slow = ema_series(closes, 26)
    if fast is None or slow is None:
        return None, None
    macd_line = fast - slow
    valid = macd_line[~np.isnan(macd_line)]
    if len(valid) < 9:
        return None, None
    macd_arr = list(valid)
    sig = ema_val(macd_arr, 9)
    return float(macd_arr[-1]), sig


def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    """Average True Range — used for stop placement."""
    if len(closes) < period + 1:
        return None
    h = _arr(highs[-period - 1:])
    l = _arr(lows[-period - 1:])
    c = _arr(closes[-period - 1:])
    prev_c = c[:-1]
    h2 = h[1:]
    l2 = l[1:]
    tr = np.maximum(h2 - l2, np.maximum(np.abs(h2 - prev_c), np.abs(l2 - prev_c)))
    return float(tr.mean())


def vol_ratio(volumes: List[float], lookback: int = 20) -> float:
    """Today's volume vs. 20-day average. Capped 0.3–5×."""
    if len(volumes) < 2:
        return 1.0
    avg = np.mean(volumes[-lookback - 1:-1]) if len(volumes) > lookback else np.mean(volumes[:-1])
    if avg <= 0:
        return 1.0
    return float(np.clip(volumes[-1] / avg, 0.3, 5.0))


def trend_signal(closes: List[float]) -> str:
    """price > EMA20 > EMA50 → bullish; price < EMA20 < EMA50 → bearish."""
    if len(closes) < 50:
        return "neutral"
    e20 = ema_val(closes, 20)
    e50 = ema_val(closes, 50)
    if e20 is None or e50 is None:
        return "neutral"
    last = closes[-1]
    if last > e20 > e50:
        return "bullish"
    if last < e20 < e50:
        return "bearish"
    return "neutral"


def above_vwap(closes: List[float], highs: List[float], lows: List[float], volumes: List[float], days: int = 20) -> bool:
    """Proxy VWAP over recent N days using typical price × volume."""
    n = min(days, len(closes))
    if n < 2:
        return False
    tp = [(h + l + c) / 3 for h, l, c in zip(highs[-n:], lows[-n:], closes[-n:])]
    vols = volumes[-n:]
    weighted = sum(t * v for t, v in zip(tp, vols))
    total_vol = sum(vols)
    if total_vol == 0:
        return False
    vwap = weighted / total_vol
    return closes[-1] > vwap


def pct_from_52w_high(closes: List[float]) -> float:
    """How far is current price from 52-week high (negative = below)."""
    hi = max(closes[-min(252, len(closes)):])
    if hi == 0:
        return 0.0
    return (closes[-1] - hi) / hi * 100


def consolidation_score(closes: List[float], window: int = 15) -> float:
    """Returns tightness (lower = tighter). 0.05 = 5% band in window."""
    win = closes[-window:] if len(closes) >= window else closes
    if not win or max(win) == 0:
        return 1.0
    return (max(win) - min(win)) / max(win)


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN SCORING  0-100  (each scorer returns int)
# ─────────────────────────────────────────────────────────────────────────────

def score_cup_handle(closes: List[float], vols: List[float]) -> int:
    """
    Cup & Handle:
      • Cup depth 12–35%, U-shaped recovery
      • Handle ≤ 12% pullback from cup high
      • Breakout attempt near pivot (within 3%)
      • Volume should contract during handle, expand on breakout
    """
    if len(closes) < 40:
        return 0
    # Use last 40 data points for cup
    win = closes[-40:]
    lo_idx = int(np.argmin(win))
    if lo_idx < 5 or lo_idx > 32:          # need space on both sides
        return 15
    lo = win[lo_idx]
    left_peak = max(win[:lo_idx])
    right_section = win[lo_idx:]
    right_peak_idx = int(np.argmax(right_section))
    right_peak = right_section[right_peak_idx]
    last = closes[-1]

    depth = (left_peak - lo) / left_peak if left_peak > 0 else 0
    if not (0.12 <= depth <= 0.35):
        return 20

    # Recovery quality (right side should recover ≥ 85% of left side depth)
    recovery = (right_peak - lo) / (left_peak - lo) if left_peak > lo else 0
    # Handle pullback from right peak
    handle_pb = (right_peak - last) / right_peak if right_peak > 0 else 0
    # Near pivot
    near_pivot = last > left_peak * 0.97

    score = 45
    if recovery >= 0.85:   score += 20
    if recovery >= 0.95:   score += 5
    if 0.02 <= handle_pb <= 0.12:  score += 15
    if near_pivot:         score += 10
    # Volume contraction during handle
    if len(vols) >= 10:
        handle_vol = np.mean(vols[-5:])
        cup_vol    = np.mean(vols[-20:-5])
        if handle_vol < cup_vol * 0.85:  score += 5    # quiet handle
    return min(score, 95)


def score_double_bottom(closes: List[float], vols: List[float]) -> int:
    """
    Double Bottom (W):
      • Two lows within 3% of each other, separated by a peak
      • Neckline break with expanding volume
      • RSI divergence proxy: second dip at lower price but score ignores RSI
        (already factored into reasoning)
    """
    if len(closes) < 30:
        return 0
    win = closes[-30:]
    n = len(win)
    mid = n // 2
    lo1 = min(win[:mid])
    lo2 = min(win[mid:])
    neckline = max(win[mid - 4:mid + 4]) if mid >= 4 else max(win)
    last = closes[-1]

    if lo1 == 0 or lo2 == 0:
        return 0

    similarity = 1 - abs(lo1 - lo2) / ((lo1 + lo2) / 2)
    if similarity < 0.90:    # lows must be within ~10%
        return 15

    score = 45
    if similarity >= 0.97:   score += 15   # near-identical lows
    elif similarity >= 0.93: score += 8
    if last > neckline:      score += 20   # confirmed neckline break
    if last > lo2 * 1.05:    score += 10   # 5% above second low

    # Volume should rise on second-bottom bounce
    if len(vols) >= 10:
        recent_vol = np.mean(vols[-5:])
        prior_vol  = np.mean(vols[-20:-5])
        if recent_vol > prior_vol * 1.1:  score += 5

    return min(score, 92)


def score_ipo_base(closes: List[float], listing_age: int) -> int:
    """
    IPO Base (First Base):
      • Stock listed within ~2 years
      • Consolidates <20% from post-IPO high in 4-6 week range
      • Price near top of base (constructive)
    """
    if listing_age > 730 or len(closes) < 15:
        return 0
    win = closes[-25:] if len(closes) >= 25 else closes
    peak = max(win)
    lo   = min(win)
    last = closes[-1]
    depth = (peak - lo) / peak if peak > 0 else 1.0

    if depth > 0.30:
        return 15

    score = 50
    if depth < 0.15: score += 15
    if depth < 0.10: score += 5
    if last > peak * 0.93: score += 15    # near top of base
    if last > peak * 0.98: score += 5     # at pivot
    if listing_age < 365:  score += 5     # truly first base
    # Tightness of range
    tightness = consolidation_score(closes[-15:] if len(closes) >= 15 else closes)
    if tightness < 0.08: score += 5
    return min(score, 90)


def score_momentum(closes: List[float], vols: List[float]) -> int:
    """
    Momentum Breakout:
      • Price > EMA20 > EMA50 (uptrend structure)
      • Within 5% of 52-week high
      • RSI 55-75 power zone
      • Volume expansion
    """
    if len(closes) < 55:
        return 0
    e20 = ema_val(closes, 20)
    e50 = ema_val(closes, 50)
    if e20 is None or e50 is None:
        return 0

    last = closes[-1]
    pct_hi = pct_from_52w_high(closes)   # 0 = at high, negative = below
    r = rsi_wilder(closes)

    score = 25
    if last > e20:           score += 15
    if e20 > e50:            score += 15
    if last > e50 * 1.05:    score += 5    # well above 50EMA
    if pct_hi >= -5:         score += 15   # near 52w high
    elif pct_hi >= -10:      score += 8
    if r and 55 <= r <= 75:  score += 12
    elif r and r > 75:       score += 3    # overbought, lower score
    if len(vols) >= 5:
        vr = vol_ratio(vols)
        if vr >= 1.5:        score += 10
        elif vr >= 1.2:      score += 5
    return min(score, 92)


def score_flat_base(closes: List[float], vols: List[float]) -> int:
    """
    Flat Base / Darvas Box:
      • Last 5-7 weeks tight consolidation < 15% range
      • Contraction of volume during base
      • Price in upper half of the base (strength)
      • Prior uptrend before base
    """
    if len(closes) < 30:
        return 0
    # Base = last 25 bars; ensure prior trend exists before it
    base_win = closes[-25:]
    prior_win = closes[-50:-25] if len(closes) >= 50 else closes[:max(1, len(closes) // 2)]
    peak  = max(base_win)
    lo    = min(base_win)
    last  = closes[-1]
    band  = (peak - lo) / peak if peak > 0 else 1.0

    if band > 0.15:
        return 20

    prior_avg = float(np.mean(prior_win)) if prior_win else closes[-1]
    prior_trend = prior_avg < min(base_win)   # base sits on top of prior rally

    score = 50
    if band < 0.10: score += 15
    if band < 0.07: score += 8
    if last > (peak + lo) / 2: score += 10  # in upper half
    if last > peak * 0.97:     score += 5   # at pivot
    if prior_trend:            score += 5   # built on prior uptrend
    # Volume should dry up during base
    if len(vols) >= 25:
        base_vol  = np.mean(vols[-25:])
        prior_vol = np.mean(vols[-50:-25]) if len(vols) >= 50 else np.mean(vols[:-25])
        if base_vol < prior_vol * 0.8: score += 7  # volume drying up = healthy
    return min(score, 88)


# ─────────────────────────────────────────────────────────────────────────────
# FETCH DATA VIA YFINANCE
# ─────────────────────────────────────────────────────────────────────────────
_quote_cache: Dict[str, Tuple[float, Optional[dict]]] = {}
CACHE_TTL_QUOTE = 120    # 2 min for single quotes
CACHE_TTL_UNIVERSE = 300  # 5 min for full universe scan
_universe_cache: Tuple[float, List[dict]] = (0.0, [])


def fetch_stock_data(yf_symbol: str) -> Optional[dict]:
    """
    Fetch 1 year of daily OHLCV via yfinance and return a data dict.
    Returns None on error or insufficient data.
    """
    ts = time.time()
    cached = _quote_cache.get(yf_symbol)
    if cached and (ts - cached[0]) < CACHE_TTL_QUOTE:
        return cached[1]
    try:
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period="1y", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 20:
            log.warning(f"Insufficient data for {yf_symbol}")
            _quote_cache[yf_symbol] = (ts, None)
            return None

        closes  = hist["Close"].tolist()
        opens   = hist["Open"].tolist()
        highs   = hist["High"].tolist()
        lows    = hist["Low"].tolist()
        volumes = hist["Volume"].tolist()

        # Current price (last close) and daily change
        last_price   = closes[-1]
        prev_price   = closes[-2] if len(closes) >= 2 else closes[-1]
        change_pct   = (last_price - prev_price) / prev_price * 100 if prev_price else 0.0

        result = {
            "closes": closes,
            "opens": opens,
            "highs": highs,
            "lows": lows,
            "volumes": volumes,
            "last_price": float(last_price),
            "change_pct": float(change_pct),
        }
        _quote_cache[yf_symbol] = (ts, result)
        return result

    except Exception as e:
        log.warning(f"yfinance fetch failed for {yf_symbol}: {e}")
        _quote_cache[yf_symbol] = (ts, None)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY METADATA
# ─────────────────────────────────────────────────────────────────────────────
STRATEGY_IDS = ["cup", "dbl", "ipo", "mom", "flat"]
STRATEGY_META = {
    "cup":  {"name": "Cup & Handle",      "rr": 2.5, "tgt_pct": 0.17, "stop_pct": 0.07},
    "dbl":  {"name": "Double Bottom",     "rr": 2.2, "tgt_pct": 0.13, "stop_pct": 0.055},
    "ipo":  {"name": "IPO Base",          "rr": 2.0, "tgt_pct": 0.11, "stop_pct": 0.05},
    "mom":  {"name": "Momentum Breakout", "rr": 2.5, "tgt_pct": 0.14, "stop_pct": 0.06},
    "flat": {"name": "Flat Base",         "rr": 1.8, "tgt_pct": 0.10, "stop_pct": 0.055},
}


# ─────────────────────────────────────────────────────────────────────────────
# ANALYZE A SINGLE STOCK
# ─────────────────────────────────────────────────────────────────────────────
def analyze_stock(yf_sym: str, display_sym: str, company: str, sector: str, cap: str, listing_age: int) -> Optional[dict]:
    data = fetch_stock_data(yf_sym)
    if not data:
        return None

    closes  = data["closes"]
    highs   = data["highs"]
    lows    = data["lows"]
    volumes = data["volumes"]
    price   = data["last_price"]
    chg_pct = data["change_pct"]

    if len(closes) < 20:
        return None

    # Indicators
    r       = rsi_wilder(closes) or 50.0
    trend   = trend_signal(closes)
    vr      = vol_ratio(volumes)
    pct_hi  = pct_from_52w_high(closes)
    macd_v, macd_sig = macd_signal(closes)
    atr_v   = atr(highs, lows, closes)
    over_vwap = above_vwap(closes, highs, lows, volumes)
    tight     = consolidation_score(closes)

    scores = {
        "cup":  score_cup_handle(closes, volumes),
        "dbl":  score_double_bottom(closes, volumes),
        "ipo":  score_ipo_base(closes, listing_age),
        "mom":  score_momentum(closes, volumes),
        "flat": score_flat_base(closes, volumes),
    }

    return {
        "symbol":       display_sym,
        "yf_symbol":    yf_sym,
        "company":      company,
        "sector":       sector,
        "cap":          cap,
        "price":        round(price, 2),
        "change_pct":   round(chg_pct, 2),
        "rsi":          round(r, 1),
        "vol_ratio":    round(vr, 2),
        "trend":        trend,
        "pct_from_52w_high": round(pct_hi, 1),
        "macd":         round(macd_v, 3) if macd_v is not None else None,
        "macd_signal":  round(macd_sig, 3) if macd_sig is not None else None,
        "atr":          round(atr_v, 2) if atr_v is not None else None,
        "above_vwap":   over_vwap,
        "tightness":    round(tight, 3),
        "scores":       scores,
        "listing_age_days": listing_age,
    }


# ─────────────────────────────────────────────────────────────────────────────
# UNIVERSE BUILDER (threaded via asyncio.to_thread)
# ─────────────────────────────────────────────────────────────────────────────
async def build_universe() -> List[dict]:
    global _universe_cache
    now = time.time()
    if _universe_cache[1] and (now - _universe_cache[0]) < CACHE_TTL_UNIVERSE:
        log.info("Returning cached universe.")
        return _universe_cache[1]

    log.info(f"Analyzing {len(UNIVERSE)} stocks via yfinance…")

    sem = asyncio.Semaphore(8)  # yfinance is thread-safe; 8 concurrent fetches

    async def gated(entry):
        async with sem:
            yf_sym, disp, company, sector, cap, age = entry
            return await asyncio.to_thread(analyze_stock, yf_sym, disp, company, sector, cap, age)

    results = await asyncio.gather(*[gated(e) for e in UNIVERSE], return_exceptions=True)
    analyzed = [r for r in results if r and not isinstance(r, Exception)]
    log.info(f"Analyzed {len(analyzed)}/{len(UNIVERSE)} stocks successfully.")
    _universe_cache = (now, analyzed)
    return analyzed


# ─────────────────────────────────────────────────────────────────────────────
# REASONING GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
def build_reasoning(stock: dict, strat_id: str) -> List[str]:
    r = []
    meta = STRATEGY_META[strat_id]
    rsi_v   = stock["rsi"]
    vr      = stock["vol_ratio"]
    trend   = stock["trend"]
    pct_hi  = stock["pct_from_52w_high"]
    macd_v  = stock["macd"]
    macd_s  = stock["macd_signal"]
    vwap    = stock["above_vwap"]

    if strat_id == "cup":
        r.append(f"<b>Cup & Handle</b> pattern — rounded base with handle pullback near pivot")
        r.append(f"Fit score <b>{stock['scores']['cup']}/100</b> — structure meets institutional criteria")
        if vr >= 1.5:
            r.append(f"Volume at <b>{vr:.1f}×</b> 20-day average — accumulation signature confirmed")
        elif vr >= 1.2:
            r.append(f"Volume <b>{vr:.1f}×</b> above average — healthy buying interest")
        if 55 <= rsi_v <= 75:
            r.append(f"RSI (Wilder) <b>{rsi_v}</b> — power zone, not overbought")
        elif rsi_v > 75:
            r.append(f"RSI <b>{rsi_v}</b> — extended; ideal entry on handle dip")
        if trend == "bullish":
            r.append(f"<b>Bullish</b> trend confirmed: Price > EMA20 > EMA50")
        if macd_v is not None and macd_s is not None and macd_v > macd_s:
            r.append(f"MACD <b>above signal</b> — momentum expanding")
        if vwap:
            r.append(f"Trading <b>above VWAP</b> — institutional demand on spot")
        r.append(f"Typical R/R <b>{meta['rr']}×</b> · Target +{int(meta['tgt_pct']*100)}% · Stop -{int(meta['stop_pct']*100)}%")

    elif strat_id == "dbl":
        r.append(f"<b>Double Bottom (W)</b> — two lows at similar support level")
        r.append(f"Fit score <b>{stock['scores']['dbl']}/100</b>")
        if rsi_v < 45:
            r.append(f"RSI <b>{rsi_v}</b> — potential bullish divergence at second low")
        else:
            r.append(f"RSI <b>{rsi_v}</b> — momentum already shifting higher")
        if vr >= 1.3:
            r.append(f"Volume <b>{vr:.1f}×</b> — validates breakout from neckline")
        if macd_v is not None and macd_s is not None and macd_v > macd_s:
            r.append(f"MACD crossover <b>bullish</b> — histogram expanding")
        if trend == "bullish":
            r.append(f"Primary trend: <b>Bullish</b> — reversion aligned with uptrend")
        r.append(f"Measured-move target: <b>+10–16%</b> · Stop below second low · R/R <b>{meta['rr']}×</b>")

    elif strat_id == "ipo":
        r.append(f"<b>First IPO Base</b> — institutional accumulation post listing")
        r.append(f"Listed ~{stock['listing_age_days']} days ago — inside 2-year IPO window")
        r.append(f"Fit score <b>{stock['scores']['ipo']}/100</b> — tight price action, coiling energy")
        if trend == "bullish":
            r.append(f"Primary uptrend intact — first bases historically deliver explosive moves")
        if stock["tightness"] < 0.10:
            r.append(f"Range tightness <b>{stock['tightness']*100:.1f}%</b> — very tight consolidation")
        r.append(f"RSI <b>{rsi_v}</b> · Historic avg IPO-base breakout: <b>7–20%</b> move")
        r.append(f"R/R <b>{meta['rr']}×</b> · Stop -{int(meta['stop_pct']*100)}% below base low")

    elif strat_id == "mom":
        r.append(f"<b>Momentum Breakout</b> — price clearing multi-month resistance")
        r.append(f"Fit score <b>{stock['scores']['mom']}/100</b>")
        r.append(f"Trend: <b>{trend.upper()}</b> — EMAs aligned for trend follow")
        r.append(f"<b>{abs(pct_hi):.1f}%</b> from 52-week high — {'at new highs' if pct_hi >= -2 else 'approaching breakout zone'}")
        if 55 <= rsi_v <= 75:
            r.append(f"RSI <b>{rsi_v}</b> — in the 55–75 momentum power zone")
        elif rsi_v > 75:
            r.append(f"RSI <b>{rsi_v}</b> — extended; wait for shallow pullback to EMA20")
        if vr >= 1.5:
            r.append(f"Volume surge <b>{vr:.1f}×</b> — institutional conviction behind move")
        if macd_v is not None and macd_s is not None and macd_v > macd_s:
            r.append(f"MACD <b>bullish crossover</b> confirmed")
        r.append(f"Ride with trailing stop · Typical move <b>10–18%</b> · R/R <b>{meta['rr']}×</b>")

    else:  # flat
        r.append(f"<b>Flat Base / Darvas Box</b> — tight sideways consolidation on prior rally")
        r.append(f"Fit score <b>{stock['scores']['flat']}/100</b>")
        r.append(f"Range tightness: <b>{stock['tightness']*100:.1f}%</b> — optimal base compression")
        if vr >= 1.3:
            r.append(f"Volume <b>{vr:.1f}×</b> — institutional footprint inside box")
        elif vr < 0.9:
            r.append(f"Volume drying up (<b>{vr:.1f}×</b>) — healthy base building in progress")
        if trend == "bullish":
            r.append(f"Built on <b>bullish</b> structure (Price > EMA20 > EMA50)")
        if macd_v is not None and macd_v > 0:
            r.append(f"MACD positive — underlying momentum constructive")
        if vwap:
            r.append(f"Above VWAP — demand outpacing supply")
        r.append(f"Breakout targets <b>+8–14%</b> · Stop under box floor · R/R <b>{meta['rr']}×</b>")

    return r


def calc_levels(price: float, strat_id: str, atr_val: Optional[float] = None) -> dict:
    m = STRATEGY_META[strat_id]
    # If ATR is available use it to refine stop (2 ATR vs. pct-based, whichever is tighter)
    stop_pct = m["stop_pct"]
    if atr_val and price > 0:
        atr_stop_pct = (atr_val * 2) / price
        stop_pct = min(stop_pct, max(atr_stop_pct, 0.02))  # floor 2%
    return {
        "entry":    round(price, 2),
        "target":   round(price * (1 + m["tgt_pct"]), 2),
        "stop":     round(price * (1 - stop_pct), 2),
        "tgt_pct":  round(m["tgt_pct"] * 100, 1),
        "stop_pct": round(stop_pct * 100, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="SWING Terminal API", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.on_event("startup")
async def warmup():
    """Pre-warm the universe cache in background so first user scan is fast."""
    log.info("Startup warmup: pre-fetching universe…")
    asyncio.create_task(build_universe())


@app.get("/")
async def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "ok", "service": "swing-terminal-v2", "time": datetime.utcnow().isoformat()}


@app.get("/api/health")
async def health():
    cached_count = len(_universe_cache[1])
    return {
        "ok": True,
        "universe_cached": cached_count,
        "cache_age_s": round(time.time() - _universe_cache[0], 0) if _universe_cache[1] else None,
    }


@app.get("/api/strategies")
async def strategies():
    return [
        {"id": "cup",  "rank": "S-01", "name": "Cup & Handle",      "win": "65–85%", "avg": "14–20%", "rr": 2.5},
        {"id": "dbl",  "rank": "S-02", "name": "Double Bottom",     "win": "70–80%", "avg": "10–16%", "rr": 2.2},
        {"id": "ipo",  "rank": "S-03", "name": "IPO Base",          "win": "65–75%", "avg": "7–15%",  "rr": 2.0},
        {"id": "mom",  "rank": "S-04", "name": "Momentum Breakout", "win": "60–80%", "avg": "10–18%", "rr": 2.5},
        {"id": "flat", "rank": "S-05", "name": "Flat Base",         "win": "60–70%", "avg": "8–14%",  "rr": 1.8},
    ]


class ScanParams(BaseModel):
    strategy: str
    cap: str = "any"
    sector: str = "any"
    min_score: int = 0
    min_rr: float = 0
    trend: str = "any"
    volume_confirmed: bool = False


@app.post("/api/scan")
async def scan(params: ScanParams):
    if params.strategy not in STRATEGY_IDS:
        raise HTTPException(400, f"Unknown strategy: {params.strategy}")

    stocks = await build_universe()
    if not stocks:
        raise HTTPException(503, "Universe not ready yet. Try again in 30 seconds.")

    meta = STRATEGY_META[params.strategy]
    results = []

    for s in stocks:
        score = s["scores"].get(params.strategy, 0)
        min_threshold = max(params.min_score, 35)
        if score < min_threshold:
            continue
        if params.cap != "any" and s["cap"] != params.cap:
            continue
        if params.sector != "any" and s["sector"] != params.sector:
            continue
        if params.min_rr > 0 and meta["rr"] < params.min_rr:
            continue
        if params.trend != "any" and s["trend"] != params.trend:
            continue
        if params.volume_confirmed and s["vol_ratio"] < 1.3:
            continue

        levels    = calc_levels(s["price"], params.strategy, s.get("atr"))
        reasoning = build_reasoning(s, params.strategy)
        results.append({
            **s,
            "fit_score":     score,
            "strategy_meta": meta,
            "levels":        levels,
            "reasoning":     reasoning,
        })

    results.sort(key=lambda x: x["fit_score"], reverse=True)
    return {
        "strategy":       params.strategy,
        "count":          len(results),
        "total_analyzed": len(stocks),
        "results":        results[:30],
    }


@app.get("/api/quote/{symbol}")
async def single_quote(symbol: str):
    """Quick quote for a single NSE symbol (appends .NS automatically)."""
    yf_sym = symbol.upper() + ".NS" if not symbol.upper().endswith(".NS") else symbol.upper()
    data = await asyncio.to_thread(fetch_stock_data, yf_sym)
    if not data:
        raise HTTPException(404, f"Quote unavailable for {symbol}")
    return {
        "symbol":     symbol.upper(),
        "price":      data["last_price"],
        "change_pct": round(data["change_pct"], 2),
        "bars":       len(data["closes"]),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
