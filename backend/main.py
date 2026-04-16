"""
SWING Terminal — FastAPI backend v3
Data: yfinance (works from any cloud IP)
Architecture: background universe refresh + fast synchronous scan
- On startup: immediately begin fetching universe in background thread
- /api/scan: returns whatever is cached instantly; if cache empty, waits up to 25s
- /api/status: shows cache health
"""
import os
import time
import logging
import asyncio
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

import numpy as np
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("swing")

# ─────────────────────────────────────────────────────────────────────────────
# UNIVERSE  (yfinance tickers → .NS suffix for NSE)
# ─────────────────────────────────────────────────────────────────────────────
UNIVERSE = [
    ("TCS.NS",         "TCS",         "Tata Consultancy Services",    "Information Technology", "large", 5500),
    ("INFY.NS",        "INFY",        "Infosys",                      "Information Technology", "large", 8000),
    ("WIPRO.NS",       "WIPRO",       "Wipro",                        "Information Technology", "large", 8000),
    ("HCLTECH.NS",     "HCLTECH",     "HCL Technologies",             "Information Technology", "large", 7000),
    ("TECHM.NS",       "TECHM",       "Tech Mahindra",                "Information Technology", "large", 5500),
    ("LTIM.NS",        "LTIM",        "LTIMindtree",                  "Information Technology", "mid",    900),
    ("PERSISTENT.NS",  "PERSISTENT",  "Persistent Systems",           "Information Technology", "mid",   4500),
    ("COFORGE.NS",     "COFORGE",     "Coforge",                      "Information Technology", "mid",   5000),
    ("KPITTECH.NS",    "KPITTECH",    "KPIT Technologies",            "Information Technology", "small", 1800),
    ("TATAELXSI.NS",   "TATAELXSI",  "Tata Elxsi",                   "Information Technology", "mid",   7000),
    ("HAPPSTMNDS.NS",  "HAPPSTMNDS",  "Happiest Minds Technologies",  "Information Technology", "small", 1500),
    ("HDFCBANK.NS",    "HDFCBANK",    "HDFC Bank",                    "Banking & Financials",   "large", 9000),
    ("ICICIBANK.NS",   "ICICIBANK",   "ICICI Bank",                   "Banking & Financials",   "large", 9000),
    ("AXISBANK.NS",    "AXISBANK",    "Axis Bank",                    "Banking & Financials",   "large", 8500),
    ("KOTAKBANK.NS",   "KOTAKBANK",   "Kotak Mahindra Bank",          "Banking & Financials",   "large", 8000),
    ("SBIN.NS",        "SBIN",        "State Bank of India",          "Banking & Financials",   "large", 9000),
    ("BAJFINANCE.NS",  "BAJFINANCE",  "Bajaj Finance",                "Banking & Financials",   "large", 6000),
    ("BAJAJFINSV.NS",  "BAJAJFINSV",  "Bajaj Finserv",                "Banking & Financials",   "large", 5500),
    ("CDSL.NS",        "CDSL",        "Central Depository Services",  "Banking & Financials",   "small", 2800),
    ("RELIANCE.NS",    "RELIANCE",    "Reliance Industries",          "Energy",                 "large", 9000),
    ("ONGC.NS",        "ONGC",        "ONGC",                         "Energy",                 "large", 8500),
    ("IOC.NS",         "IOC",         "Indian Oil Corporation",       "Energy",                 "large", 8000),
    ("BPCL.NS",        "BPCL",        "Bharat Petroleum",             "Energy",                 "large", 8000),
    ("IEX.NS",         "IEX",         "Indian Energy Exchange",       "Energy",                 "mid",   1500),
    ("POWERGRID.NS",   "POWERGRID",   "Power Grid Corporation",       "Energy",                 "large", 5000),
    ("SUNPHARMA.NS",   "SUNPHARMA",   "Sun Pharmaceutical",           "Pharmaceuticals",        "large", 8000),
    ("DRREDDY.NS",     "DRREDDY",     "Dr Reddy's Laboratories",      "Pharmaceuticals",        "large", 8500),
    ("CIPLA.NS",       "CIPLA",       "Cipla",                        "Pharmaceuticals",        "large", 8500),
    ("LUPIN.NS",       "LUPIN",       "Lupin",                        "Pharmaceuticals",        "mid",   7500),
    ("MANKIND.NS",     "MANKIND",     "Mankind Pharma",               "Pharmaceuticals",        "mid",    900),
    ("METROPOLIS.NS",  "METROPOLIS",  "Metropolis Healthcare",        "Pharmaceuticals",        "small", 2500),
    ("MARUTI.NS",      "MARUTI",      "Maruti Suzuki India",          "Auto & Ancillaries",     "large", 7500),
    ("M&M.NS",         "M&M",         "Mahindra & Mahindra",          "Auto & Ancillaries",     "large", 8500),
    ("TATAMOTORS.NS",  "TATAMOTORS",  "Tata Motors",                  "Auto & Ancillaries",     "large", 9000),
    ("BAJAJ-AUTO.NS",  "BAJAJ-AUTO",  "Bajaj Auto",                   "Auto & Ancillaries",     "large", 6000),
    ("EICHERMOT.NS",   "EICHERMOT",   "Eicher Motors",                "Auto & Ancillaries",     "large", 7000),
    ("SONACOMS.NS",    "SONACOMS",    "Sona BLW Precision",           "Auto & Ancillaries",     "mid",   1700),
    ("ITC.NS",         "ITC",         "ITC",                          "FMCG",                   "large", 9000),
    ("HINDUNILVR.NS",  "HINDUNILVR",  "Hindustan Unilever",           "FMCG",                   "large", 9000),
    ("NESTLEIND.NS",   "NESTLEIND",   "Nestle India",                 "FMCG",                   "large", 8500),
    ("BRITANNIA.NS",   "BRITANNIA",   "Britannia Industries",         "FMCG",                   "large", 8500),
    ("DABUR.NS",       "DABUR",       "Dabur India",                  "FMCG",                   "large", 8500),
    ("ASIANPAINT.NS",  "ASIANPAINT",  "Asian Paints",                 "FMCG",                   "large", 8500),
    ("MARICO.NS",      "MARICO",      "Marico",                       "FMCG",                   "large", 7000),
    ("LT.NS",          "LT",          "Larsen & Toubro",              "Capital Goods",           "large", 8500),
    ("ULTRACEMCO.NS",  "ULTRACEMCO",  "UltraTech Cement",             "Capital Goods",           "large", 7000),
    ("POLYCAB.NS",     "POLYCAB",     "Polycab India",                "Capital Goods",           "mid",   2300),
    ("ASTRAL.NS",      "ASTRAL",      "Astral Ltd",                   "Capital Goods",           "mid",   5500),
    ("IRCTC.NS",       "IRCTC",       "Indian Railway Catering",      "Capital Goods",           "mid",   2300),
    ("TATASTEEL.NS",   "TATASTEEL",   "Tata Steel",                   "Metals",                 "large", 9000),
    ("JSWSTEEL.NS",    "JSWSTEEL",    "JSW Steel",                    "Metals",                 "large", 7000),
    ("HINDALCO.NS",    "HINDALCO",    "Hindalco Industries",          "Metals",                 "large", 8000),
    ("TITAN.NS",       "TITAN",       "Titan Company",                "Consumer Durables",       "large", 8000),
    ("VOLTAS.NS",      "VOLTAS",      "Voltas",                       "Consumer Durables",       "mid",   8000),
    ("DIXON.NS",       "DIXON",       "Dixon Technologies",           "Consumer Durables",       "mid",   1900),
    ("ZOMATO.NS",      "ZOMATO",      "Zomato",                       "Consumer Durables",       "mid",   1700),
    ("TRENT.NS",       "TRENT",       "Trent",                        "Consumer Durables",       "mid",   8000),
    ("PIIND.NS",       "PIIND",       "PI Industries",                "Chemicals",               "mid",   6000),
    ("SRF.NS",         "SRF",         "SRF",                          "Chemicals",               "mid",   7000),
    ("DEEPAKNTR.NS",   "DEEPAKNTR",   "Deepak Nitrite",               "Chemicals",               "mid",   6000),
    ("NAVINFLUOR.NS",  "NAVINFLUOR",  "Navin Fluorine",               "Chemicals",               "mid",   7000),
]

# ─────────────────────────────────────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────────────────────────────────────
def rsi_wilder(closes: List[float], period: int = 14) -> Optional[float]:
    arr = np.array(closes, dtype=np.float64)
    if len(arr) < period + 1:
        return None
    d = np.diff(arr)
    g = np.where(d > 0, d, 0.0)
    l = np.where(d < 0, -d, 0.0)
    ag = g[:period].mean()
    al = l[:period].mean()
    for gi, li in zip(g[period:], l[period:]):
        ag = (ag * (period - 1) + gi) / period
        al = (al * (period - 1) + li) / period
    if al == 0:
        return 100.0
    return float(100 - 100 / (1 + ag / al))


def ema_val(closes: List[float], period: int) -> Optional[float]:
    arr = np.array(closes, dtype=np.float64)
    if len(arr) < period:
        return None
    k = 2.0 / (period + 1)
    e = arr[:period].mean()
    for x in arr[period:]:
        e = x * k + e * (1 - k)
    return float(e)


def macd_hist(closes: List[float]) -> Optional[float]:
    """Returns MACD histogram (MACD - Signal). Positive = bullish."""
    if len(closes) < 35:
        return None
    arr = np.array(closes, dtype=np.float64)
    k12 = 2 / 13; k26 = 2 / 27; k9 = 2 / 10
    e12 = arr[:12].mean(); e26 = arr[:26].mean()
    macd_arr = []
    for x in arr[12:]:
        e12 = x * k12 + e12 * (1 - k12)
    for x in arr[26:]:
        e26 = x * k26 + e26 * (1 - k26)
        macd_arr.append(e12 - e26)
    if len(macd_arr) < 9:
        return None
    sig = np.mean(macd_arr[-9:])
    e_sig = sig
    k9_val = 2 / 10
    for m in macd_arr[-9:]:
        e_sig = m * k9_val + e_sig * (1 - k9_val)
    return float(macd_arr[-1] - e_sig)


def vol_ratio_fn(volumes: List[float], lookback: int = 20) -> float:
    if len(volumes) < 2:
        return 1.0
    avg = np.mean(volumes[-lookback - 1:-1]) if len(volumes) > lookback else np.mean(volumes[:-1])
    if avg <= 0:
        return 1.0
    return float(np.clip(volumes[-1] / avg, 0.3, 5.0))


def trend_signal(closes: List[float]) -> str:
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


def pct_from_52w_high(closes: List[float]) -> float:
    hi = max(closes[-min(252, len(closes)):])
    if hi == 0:
        return 0.0
    return round((closes[-1] - hi) / hi * 100, 1)


def tightness(closes: List[float], window: int = 15) -> float:
    win = closes[-window:] if len(closes) >= window else closes
    if not win or max(win) == 0:
        return 1.0
    return (max(win) - min(win)) / max(win)


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN SCORERS
# ─────────────────────────────────────────────────────────────────────────────
def score_cup_handle(closes, vols) -> int:
    if len(closes) < 40:
        return 0
    win = closes[-40:]
    lo_idx = int(np.argmin(win))
    if lo_idx < 5 or lo_idx > 32:
        return 15
    lo = win[lo_idx]
    left_peak = max(win[:lo_idx])
    right_sec = win[lo_idx:]
    right_peak = max(right_sec)
    last = closes[-1]
    depth = (left_peak - lo) / left_peak if left_peak > 0 else 0
    if not (0.12 <= depth <= 0.35):
        return 20
    recovery = (right_peak - lo) / (left_peak - lo) if left_peak > lo else 0
    handle_pb = (right_peak - last) / right_peak if right_peak > 0 else 0
    score = 45
    if recovery >= 0.85: score += 20
    if recovery >= 0.95: score += 5
    if 0.02 <= handle_pb <= 0.12: score += 15
    if last > left_peak * 0.97: score += 10
    if len(vols) >= 20:
        if np.mean(vols[-5:]) < np.mean(vols[-20:-5]) * 0.85: score += 5
    return min(score, 95)


def score_double_bottom(closes, vols) -> int:
    if len(closes) < 30:
        return 0
    win = closes[-30:]
    mid = len(win) // 2
    lo1 = min(win[:mid])
    lo2 = min(win[mid:])
    if lo1 == 0 or lo2 == 0:
        return 0
    neckline = max(win[mid - 4:mid + 4]) if mid >= 4 else max(win)
    last = closes[-1]
    similarity = 1 - abs(lo1 - lo2) / ((lo1 + lo2) / 2)
    if similarity < 0.90:
        return 15
    score = 45
    if similarity >= 0.97: score += 15
    elif similarity >= 0.93: score += 8
    if last > neckline: score += 20
    if last > lo2 * 1.05: score += 10
    if len(vols) >= 10:
        if np.mean(vols[-5:]) > np.mean(vols[-20:-5]) * 1.1: score += 5
    return min(score, 92)


def score_ipo_base(closes, listing_age) -> int:
    if listing_age > 730 or len(closes) < 15:
        return 0
    win = closes[-25:] if len(closes) >= 25 else closes
    peak = max(win); lo = min(win); last = closes[-1]
    depth = (peak - lo) / peak if peak > 0 else 1.0
    if depth > 0.30:
        return 15
    score = 50
    if depth < 0.15: score += 15
    if depth < 0.10: score += 5
    if last > peak * 0.93: score += 15
    if last > peak * 0.98: score += 5
    if listing_age < 365: score += 5
    if tightness(closes[-15:] if len(closes) >= 15 else closes) < 0.08: score += 5
    return min(score, 90)


def score_momentum(closes, vols) -> int:
    if len(closes) < 55:
        return 0
    e20 = ema_val(closes, 20)
    e50 = ema_val(closes, 50)
    if e20 is None or e50 is None:
        return 0
    last = closes[-1]
    pct_hi = pct_from_52w_high(closes)
    r = rsi_wilder(closes)
    score = 25
    if last > e20: score += 15
    if e20 > e50: score += 15
    if pct_hi >= -5: score += 15
    elif pct_hi >= -10: score += 8
    if r and 55 <= r <= 75: score += 12
    elif r and r > 75: score += 3
    if len(vols) >= 5:
        vr = vol_ratio_fn(vols)
        if vr >= 1.5: score += 10
        elif vr >= 1.2: score += 5
    return min(score, 92)


def score_flat_base(closes, vols) -> int:
    if len(closes) < 30:
        return 0
    base_win = closes[-25:]
    peak = max(base_win); lo = min(base_win); last = closes[-1]
    band = (peak - lo) / peak if peak > 0 else 1.0
    if band > 0.15:
        return 20
    score = 50
    if band < 0.10: score += 15
    if band < 0.07: score += 8
    if last > (peak + lo) / 2: score += 10
    if last > peak * 0.97: score += 5
    if len(closes) >= 50:
        prior = np.mean(closes[-50:-25])
        if prior < lo: score += 5
    if len(vols) >= 25:
        if np.mean(vols[-25:]) < np.mean(vols[-50:-25] if len(vols) >= 50 else vols[:-25]) * 0.8:
            score += 7
    return min(score, 88)


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHING (synchronous — called from thread pool)
# ─────────────────────────────────────────────────────────────────────────────
def fetch_and_analyze(entry: tuple) -> Optional[dict]:
    yf_sym, disp, company, sector, cap, listing_age = entry
    try:
        ticker = yf.Ticker(yf_sym)
        hist = ticker.history(period="1y", interval="1d", auto_adjust=True)
        if hist is None or hist.empty or len(hist) < 20:
            return None
        closes  = [float(x) for x in hist["Close"].tolist()]
        highs   = [float(x) for x in hist["High"].tolist()]
        lows    = [float(x) for x in hist["Low"].tolist()]
        volumes = [float(x) for x in hist["Volume"].tolist()]

        last   = closes[-1]
        prev   = closes[-2] if len(closes) >= 2 else last
        chg    = (last - prev) / prev * 100 if prev else 0.0
        r      = rsi_wilder(closes) or 50.0
        vr     = vol_ratio_fn(volumes)
        trend  = trend_signal(closes)
        pct_hi = pct_from_52w_high(closes)
        mh     = macd_hist(closes)
        tight  = tightness(closes)

        scores = {
            "cup":  score_cup_handle(closes, volumes),
            "dbl":  score_double_bottom(closes, volumes),
            "ipo":  score_ipo_base(closes, listing_age),
            "mom":  score_momentum(closes, volumes),
            "flat": score_flat_base(closes, volumes),
        }
        return {
            "symbol":             disp,
            "company":            company,
            "sector":             sector,
            "cap":                cap,
            "price":              round(last, 2),
            "change_pct":         round(chg, 2),
            "rsi":                round(r, 1),
            "vol_ratio":          round(vr, 2),
            "trend":              trend,
            "pct_from_52w_high":  pct_hi,
            "macd_bull":          mh is not None and mh > 0,
            "tightness":          round(tight, 3),
            "scores":             scores,
            "listing_age_days":   listing_age,
        }
    except Exception as e:
        log.warning(f"fetch_and_analyze failed for {yf_sym}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL CACHE  (populated by background thread)
# ─────────────────────────────────────────────────────────────────────────────
_cache_lock = threading.Lock()
_cache: List[dict] = []
_cache_ts: float = 0.0
_cache_building: bool = False
CACHE_TTL = 300  # 5 minutes


def _build_cache_sync():
    """Runs in a background thread. Fetches all stocks and updates global cache."""
    global _cache, _cache_ts, _cache_building
    log.info(f"Background cache build started — {len(UNIVERSE)} stocks")
    results = []
    for entry in UNIVERSE:
        try:
            r = fetch_and_analyze(entry)
            if r:
                results.append(r)
        except Exception as e:
            log.warning(f"Skipping {entry[0]}: {e}")
    with _cache_lock:
        _cache = results
        _cache_ts = time.time()
        _cache_building = False
    log.info(f"Cache built: {len(results)}/{len(UNIVERSE)} stocks OK")


def trigger_cache_refresh():
    """Spawn background thread to refresh cache if stale."""
    global _cache_building
    with _cache_lock:
        if _cache_building:
            return
        _cache_building = True
    t = threading.Thread(target=_build_cache_sync, daemon=True)
    t.start()


def get_cache() -> List[dict]:
    with _cache_lock:
        return list(_cache)


def cache_age() -> float:
    with _cache_lock:
        return time.time() - _cache_ts if _cache_ts else float("inf")


def cache_count() -> int:
    with _cache_lock:
        return len(_cache)


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


def calc_levels(price: float, strat_id: str) -> dict:
    m = STRATEGY_META[strat_id]
    return {
        "entry":    round(price, 2),
        "target":   round(price * (1 + m["tgt_pct"]), 2),
        "stop":     round(price * (1 - m["stop_pct"]), 2),
        "tgt_pct":  round(m["tgt_pct"] * 100, 1),
        "stop_pct": round(m["stop_pct"] * 100, 1),
    }


def build_reasoning(s: dict, strat_id: str) -> List[str]:
    r = []
    meta = STRATEGY_META[strat_id]
    rsi_v = s["rsi"]; vr = s["vol_ratio"]; trend = s["trend"]
    pct_hi = s["pct_from_52w_high"]; macd_bull = s["macd_bull"]

    if strat_id == "cup":
        r.append(f"<b>Cup & Handle</b> — rounded base forming with U-shaped recovery")
        r.append(f"Fit score <b>{s['scores']['cup']}/100</b>")
        if vr >= 1.5: r.append(f"Volume <b>{vr:.1f}×</b> 20-day avg — strong accumulation")
        elif vr >= 1.2: r.append(f"Volume <b>{vr:.1f}×</b> — healthy buying interest")
        if 55 <= rsi_v <= 75: r.append(f"RSI <b>{rsi_v}</b> — power zone, upside room")
        if trend == "bullish": r.append("Trend: <b>Bullish</b> — Price > EMA20 > EMA50")
        if macd_bull: r.append("MACD <b>above signal</b> — momentum expanding")
        if pct_hi >= -5: r.append(f"<b>{abs(pct_hi):.1f}%</b> from 52-week high — nearing breakout")
        r.append(f"Target: +{int(meta['tgt_pct']*100)}% · Stop: -{int(meta['stop_pct']*100)}% · R/R: <b>{meta['rr']}×</b>")
    elif strat_id == "dbl":
        r.append(f"<b>Double Bottom (W)</b> — two lows at same support level")
        r.append(f"Fit score <b>{s['scores']['dbl']}/100</b>")
        if rsi_v < 45: r.append(f"RSI <b>{rsi_v}</b> — bullish divergence potential")
        else: r.append(f"RSI <b>{rsi_v}</b> — momentum turning higher")
        if vr >= 1.3: r.append(f"Volume <b>{vr:.1f}×</b> — neckline breakout validated")
        if macd_bull: r.append("MACD crossover <b>bullish</b>")
        if trend == "bullish": r.append("Primary trend: <b>Bullish</b>")
        r.append(f"Target: +{int(meta['tgt_pct']*100)}% · Stop: -{int(meta['stop_pct']*100)}% · R/R: <b>{meta['rr']}×</b>")
    elif strat_id == "ipo":
        r.append(f"<b>First IPO Base</b> — institutional accumulation post listing")
        r.append(f"Listed ~{s['listing_age_days']} days ago")
        r.append(f"Fit score <b>{s['scores']['ipo']}/100</b> — tight coil")
        if trend == "bullish": r.append("Primary uptrend intact — first bases = explosive moves")
        if s["tightness"] < 0.10: r.append(f"Range: <b>{s['tightness']*100:.1f}%</b> — very tight base")
        r.append(f"RSI <b>{rsi_v}</b> · Target: +{int(meta['tgt_pct']*100)}% · R/R: <b>{meta['rr']}×</b>")
    elif strat_id == "mom":
        r.append(f"<b>Momentum Breakout</b> — clearing multi-month resistance")
        r.append(f"Fit score <b>{s['scores']['mom']}/100</b>")
        r.append(f"{'At 52-week high' if pct_hi >= -2 else f'{abs(pct_hi):.1f}% from 52-week high'}")
        if 55 <= rsi_v <= 75: r.append(f"RSI <b>{rsi_v}</b> — momentum power zone (55–75)")
        elif rsi_v > 75: r.append(f"RSI <b>{rsi_v}</b> — extended; pullback to EMA20 ideal entry")
        if vr >= 1.5: r.append(f"Volume surge <b>{vr:.1f}×</b> — institutional conviction")
        if macd_bull: r.append("MACD <b>bullish</b> — histogram expanding")
        r.append(f"Target: +{int(meta['tgt_pct']*100)}% · Trailing stop · R/R: <b>{meta['rr']}×</b>")
    else:
        r.append(f"<b>Flat Base / Darvas Box</b> — tight consolidation on prior rally")
        r.append(f"Fit score <b>{s['scores']['flat']}/100</b> · Range: <b>{s['tightness']*100:.1f}%</b>")
        if vr < 0.9: r.append(f"Volume drying up (<b>{vr:.1f}×</b>) — healthy base in progress")
        elif vr >= 1.3: r.append(f"Volume <b>{vr:.1f}×</b> — quiet accumulation visible")
        if trend == "bullish": r.append("Built on <b>bullish</b> EMAs — constructive")
        if macd_bull: r.append("MACD positive — underlying momentum intact")
        r.append(f"Target: +{int(meta['tgt_pct']*100)}% · Stop: box floor · R/R: <b>{meta['rr']}×</b>")
    return r


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="SWING Terminal", version="3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.on_event("startup")
async def startup():
    log.info("App startup — triggering background cache build")
    trigger_cache_refresh()


@app.get("/")
async def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "ok", "version": "3.0"}


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "universe_cached": cache_count(),
        "cache_age_s": round(cache_age(), 0) if cache_count() > 0 else None,
        "building": _cache_building,
    }


@app.get("/api/status")
async def status():
    return {
        "stocks_cached": cache_count(),
        "cache_age_s": round(cache_age(), 0) if cache_count() > 0 else None,
        "building": _cache_building,
        "ready": cache_count() > 0,
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

    # If cache is empty, wait up to 25s for background build
    waited = 0
    while cache_count() == 0 and waited < 25:
        await asyncio.sleep(2)
        waited += 2

    stocks = get_cache()
    if not stocks:
        # Cache still empty — trigger refresh and return friendly error
        trigger_cache_refresh()
        raise HTTPException(503, "Data still loading. The server just woke up — try again in 30 seconds.")

    # Refresh cache in background if stale
    if cache_age() > CACHE_TTL:
        trigger_cache_refresh()

    meta = STRATEGY_META[params.strategy]
    results = []
    for s in stocks:
        score = s["scores"].get(params.strategy, 0)
        if score < max(params.min_score, 35):
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
        levels    = calc_levels(s["price"], params.strategy)
        reasoning = build_reasoning(s, params.strategy)
        results.append({**s, "fit_score": score, "strategy_meta": meta,
                        "levels": levels, "reasoning": reasoning})

    results.sort(key=lambda x: x["fit_score"], reverse=True)
    return {
        "strategy":       params.strategy,
        "count":          len(results),
        "total_analyzed": len(stocks),
        "results":        results[:30],
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
