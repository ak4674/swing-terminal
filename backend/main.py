"""
SWING Terminal — FastAPI backend v4
Data: yfinance with multiple fallback strategies to handle cloud IP blocking
- Primary: yfinance with session headers spoofing browser
- Fallback: yfinance download() batch method
- Architecture: background thread cache (no request timeouts)
"""
import os, time, logging, threading, asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import requests
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("swing")

# ─────────────────────────────────────────────────────────────────────────────
# UNIVERSE
# ─────────────────────────────────────────────────────────────────────────────
UNIVERSE = [
    ("TCS.NS",        "TCS",        "Tata Consultancy Services",   "Information Technology", "large", 5500),
    ("INFY.NS",       "INFY",       "Infosys",                     "Information Technology", "large", 8000),
    ("WIPRO.NS",      "WIPRO",      "Wipro",                       "Information Technology", "large", 8000),
    ("HCLTECH.NS",    "HCLTECH",    "HCL Technologies",            "Information Technology", "large", 7000),
    ("TECHM.NS",      "TECHM",      "Tech Mahindra",               "Information Technology", "large", 5500),
    ("LTIM.NS",       "LTIM",       "LTIMindtree",                 "Information Technology", "mid",    900),
    ("PERSISTENT.NS", "PERSISTENT", "Persistent Systems",          "Information Technology", "mid",   4500),
    ("COFORGE.NS",    "COFORGE",    "Coforge",                     "Information Technology", "mid",   5000),
    ("KPITTECH.NS",   "KPITTECH",   "KPIT Technologies",           "Information Technology", "small", 1800),
    ("TATAELXSI.NS",  "TATAELXSI",  "Tata Elxsi",                  "Information Technology", "mid",   7000),
    ("HDFCBANK.NS",   "HDFCBANK",   "HDFC Bank",                   "Banking & Financials",   "large", 9000),
    ("ICICIBANK.NS",  "ICICIBANK",  "ICICI Bank",                  "Banking & Financials",   "large", 9000),
    ("AXISBANK.NS",   "AXISBANK",   "Axis Bank",                   "Banking & Financials",   "large", 8500),
    ("KOTAKBANK.NS",  "KOTAKBANK",  "Kotak Mahindra Bank",         "Banking & Financials",   "large", 8000),
    ("SBIN.NS",       "SBIN",       "State Bank of India",         "Banking & Financials",   "large", 9000),
    ("BAJFINANCE.NS", "BAJFINANCE", "Bajaj Finance",               "Banking & Financials",   "large", 6000),
    ("BAJAJFINSV.NS", "BAJAJFINSV", "Bajaj Finserv",               "Banking & Financials",   "large", 5500),
    ("CDSL.NS",       "CDSL",       "Central Depository Services", "Banking & Financials",   "small", 2800),
    ("RELIANCE.NS",   "RELIANCE",   "Reliance Industries",         "Energy",                 "large", 9000),
    ("ONGC.NS",       "ONGC",       "ONGC",                        "Energy",                 "large", 8500),
    ("IOC.NS",        "IOC",        "Indian Oil Corporation",      "Energy",                 "large", 8000),
    ("BPCL.NS",       "BPCL",       "Bharat Petroleum",            "Energy",                 "large", 8000),
    ("IEX.NS",        "IEX",        "Indian Energy Exchange",      "Energy",                 "mid",   1500),
    ("SUNPHARMA.NS",  "SUNPHARMA",  "Sun Pharmaceutical",          "Pharmaceuticals",        "large", 8000),
    ("DRREDDY.NS",    "DRREDDY",    "Dr Reddy's Laboratories",     "Pharmaceuticals",        "large", 8500),
    ("CIPLA.NS",      "CIPLA",      "Cipla",                       "Pharmaceuticals",        "large", 8500),
    ("LUPIN.NS",      "LUPIN",      "Lupin",                       "Pharmaceuticals",        "mid",   7500),
    ("MANKIND.NS",    "MANKIND",    "Mankind Pharma",              "Pharmaceuticals",        "mid",    900),
    ("MARUTI.NS",     "MARUTI",     "Maruti Suzuki India",         "Auto & Ancillaries",     "large", 7500),
    ("M&M.NS",        "M&M",        "Mahindra & Mahindra",         "Auto & Ancillaries",     "large", 8500),
    ("TATAMOTORS.NS", "TATAMOTORS", "Tata Motors",                 "Auto & Ancillaries",     "large", 9000),
    ("BAJAJ-AUTO.NS", "BAJAJ-AUTO", "Bajaj Auto",                  "Auto & Ancillaries",     "large", 6000),
    ("EICHERMOT.NS",  "EICHERMOT",  "Eicher Motors",               "Auto & Ancillaries",     "large", 7000),
    ("ITC.NS",        "ITC",        "ITC",                         "FMCG",                   "large", 9000),
    ("HINDUNILVR.NS", "HINDUNILVR", "Hindustan Unilever",          "FMCG",                   "large", 9000),
    ("NESTLEIND.NS",  "NESTLEIND",  "Nestle India",                "FMCG",                   "large", 8500),
    ("BRITANNIA.NS",  "BRITANNIA",  "Britannia Industries",        "FMCG",                   "large", 8500),
    ("DABUR.NS",      "DABUR",      "Dabur India",                 "FMCG",                   "large", 8500),
    ("ASIANPAINT.NS", "ASIANPAINT", "Asian Paints",                "FMCG",                   "large", 8500),
    ("MARICO.NS",     "MARICO",     "Marico",                      "FMCG",                   "large", 7000),
    ("LT.NS",         "LT",         "Larsen & Toubro",             "Capital Goods",           "large", 8500),
    ("ULTRACEMCO.NS", "ULTRACEMCO", "UltraTech Cement",            "Capital Goods",           "large", 7000),
    ("POLYCAB.NS",    "POLYCAB",    "Polycab India",               "Capital Goods",           "mid",   2300),
    ("ASTRAL.NS",     "ASTRAL",     "Astral Ltd",                  "Capital Goods",           "mid",   5500),
    ("IRCTC.NS",      "IRCTC",      "Indian Railway Catering",     "Capital Goods",           "mid",   2300),
    ("TATASTEEL.NS",  "TATASTEEL",  "Tata Steel",                  "Metals",                 "large", 9000),
    ("JSWSTEEL.NS",   "JSWSTEEL",   "JSW Steel",                   "Metals",                 "large", 7000),
    ("HINDALCO.NS",   "HINDALCO",   "Hindalco Industries",         "Metals",                 "large", 8000),
    ("TITAN.NS",      "TITAN",      "Titan Company",               "Consumer Durables",       "large", 8000),
    ("VOLTAS.NS",     "VOLTAS",     "Voltas",                      "Consumer Durables",       "mid",   8000),
    ("DIXON.NS",      "DIXON",      "Dixon Technologies",          "Consumer Durables",       "mid",   1900),
    ("ZOMATO.NS",     "ZOMATO",     "Zomato",                      "Consumer Durables",       "mid",   1700),
    ("TRENT.NS",      "TRENT",      "Trent",                       "Consumer Durables",       "mid",   8000),
    ("PIIND.NS",      "PIIND",      "PI Industries",               "Chemicals",               "mid",   6000),
    ("SRF.NS",        "SRF",        "SRF",                         "Chemicals",               "mid",   7000),
    ("DEEPAKNTR.NS",  "DEEPAKNTR",  "Deepak Nitrite",              "Chemicals",               "mid",   6000),
    ("NAVINFLUOR.NS", "NAVINFLUOR", "Navin Fluorine",              "Chemicals",               "mid",   7000),
]

# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHING — uses requests directly with browser headers to bypass blocks
# ─────────────────────────────────────────────────────────────────────────────
YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://finance.yahoo.com",
    "Referer": "https://finance.yahoo.com/",
    "DNT": "1",
}

_session = requests.Session()
_session.headers.update(YAHOO_HEADERS)


def _get_crumb() -> Optional[str]:
    """Fetch Yahoo Finance crumb token needed for v8 API."""
    try:
        r = _session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=10)
        if r.status_code == 200 and r.text and r.text != "":
            return r.text.strip()
    except Exception:
        pass
    try:
        # Alternate crumb endpoint
        r = _session.get(
            "https://finance.yahoo.com/",
            headers=YAHOO_HEADERS, timeout=10
        )
        import re
        m = re.search(r'"crumb":"([^"]+)"', r.text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


_crumb: Optional[str] = None
_crumb_ts: float = 0.0


def get_crumb() -> Optional[str]:
    global _crumb, _crumb_ts
    if _crumb and (time.time() - _crumb_ts) < 3600:
        return _crumb
    _crumb = _get_crumb()
    _crumb_ts = time.time()
    return _crumb


# ─────────────────────────────────────────────────────────────────────────────
# JSON SERIALIZATION HELPER
# ─────────────────────────────────────────────────────────────────────────────
import json
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.float64, np.float32, np.float16)): return float(obj)
        if isinstance(obj, (np.int64, np.int32, np.int16, np.int8)): return int(obj)
        if isinstance(obj, (np.bool_, bool)): return bool(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        return super().default(obj)

from fastapi.responses import JSONResponse
def json_safe(data):
    return JSONResponse(content=json.loads(json.dumps(data, cls=NumpyEncoder)))


def fetch_ohlcv_yahoo(symbol: str, days: int = 365) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV from Yahoo Finance v8 chart API using browser-spoofed session.
    Returns DataFrame with columns: Open, High, Low, Close, Volume
    """
    end = int(time.time())
    start = end - days * 86400
    crumb = get_crumb()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "period1": start,
        "period2": end,
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    }
    if crumb:
        params["crumb"] = crumb

    for attempt in range(2):
        try:
            r = _session.get(url, params=params, timeout=15)
            if r.status_code == 401 and attempt == 0:
                # Crumb expired — get new one
                global _crumb
                _crumb = None
                crumb = get_crumb()
                if crumb:
                    params["crumb"] = crumb
                continue
            if r.status_code != 200:
                log.warning(f"Yahoo {symbol} HTTP {r.status_code}")
                return None
            j = r.json()
            result = j.get("chart", {}).get("result", [])
            if not result:
                return None
            res = result[0]
            timestamps = res.get("timestamp", [])
            q = res.get("indicators", {}).get("quote", [{}])[0]
            adjclose = res.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
            if not timestamps or not q.get("close"):
                return None

            df = pd.DataFrame({
                "Open":   q.get("open", []),
                "High":   q.get("high", []),
                "Low":    q.get("low", []),
                "Close":  adjclose if adjclose else q.get("close", []),
                "Volume": q.get("volume", []),
            }, index=pd.to_datetime(timestamps, unit="s"))
            df.dropna(subset=["Close"], inplace=True)
            return df if len(df) >= 20 else None
        except Exception as e:
            log.warning(f"fetch_ohlcv_yahoo {symbol} attempt {attempt}: {e}")
            time.sleep(1)
    return None


def fetch_ohlcv_stooq(symbol: str) -> Optional[pd.DataFrame]:
    """
    Fallback: Stooq.com CSV endpoint — free, no auth, no IP blocking.
    Converts NSE tickers: TCS.NS -> TCS.IN
    """
    stooq_sym = symbol.replace(".NS", ".IN").replace("&", "%26")
    url = f"https://stooq.com/q/d/l/?s={stooq_sym}&i=d"
    try:
        df = pd.read_csv(url, parse_dates=["Date"], index_col="Date")
        df = df.rename(columns={"Open": "Open", "High": "High", "Low": "Low",
                                 "Close": "Close", "Volume": "Volume"})
        df = df.sort_index()
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=365)
        df = df[df.index >= cutoff]
        df.dropna(subset=["Close"], inplace=True)
        return df if len(df) >= 20 else None
    except Exception as e:
        log.warning(f"Stooq fallback failed for {stooq_sym}: {e}")
        return None


def fetch_ohlcv(yf_symbol: str) -> Optional[pd.DataFrame]:
    """Try Yahoo first, then Stooq."""
    df = fetch_ohlcv_yahoo(yf_symbol)
    if df is not None and len(df) >= 20:
        return df
    log.info(f"Yahoo failed for {yf_symbol}, trying Stooq")
    return fetch_ohlcv_stooq(yf_symbol)


# ─────────────────────────────────────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────────────────────────────────────
def rsi_wilder(closes: List[float], period: int = 14) -> Optional[float]:
    arr = np.array(closes, dtype=np.float64)
    if len(arr) < period + 1:
        return None
    d = np.diff(arr)
    g = np.where(d > 0, d, 0.0)
    lo = np.where(d < 0, -d, 0.0)
    ag = g[:period].mean(); al = lo[:period].mean()
    for gi, li in zip(g[period:], lo[period:]):
        ag = (ag * (period - 1) + gi) / period
        al = (al * (period - 1) + li) / period
    if al == 0: return 100.0
    return float(100 - 100 / (1 + ag / al))


def ema_val(closes: List[float], period: int) -> Optional[float]:
    arr = np.array(closes, dtype=np.float64)
    if len(arr) < period: return None
    k = 2.0 / (period + 1)
    e = arr[:period].mean()
    for x in arr[period:]: e = x * k + e * (1 - k)
    return float(e)


def macd_bullish(closes: List[float]) -> bool:
    if len(closes) < 35: return False
    arr = np.array(closes, dtype=np.float64)
    k12, k26, k9 = 2/13, 2/27, 2/10
    e12 = arr[:12].mean(); e26 = arr[:26].mean()
    ml = []
    for x in arr[12:]: e12 = x*k12 + e12*(1-k12)
    for x in arr[26:]:
        e26 = x*k26 + e26*(1-k26)
        ml.append(e12 - e26)
    if len(ml) < 9: return False
    sig = np.mean(ml[-9:])
    for m in ml[-9:]: sig = m*k9 + sig*(1-k9)
    return bool(ml[-1] > sig)


def vol_ratio_fn(volumes: List[float]) -> float:
    if len(volumes) < 2: return 1.0
    avg = np.mean(volumes[-21:-1]) if len(volumes) > 20 else np.mean(volumes[:-1])
    if avg <= 0: return 1.0
    return float(np.clip(volumes[-1] / avg, 0.3, 5.0))


def trend_signal(closes: List[float]) -> str:
    if len(closes) < 50: return "neutral"
    e20 = ema_val(closes, 20); e50 = ema_val(closes, 50)
    if None in (e20, e50): return "neutral"
    last = closes[-1]
    if last > e20 > e50: return "bullish"
    if last < e20 < e50: return "bearish"
    return "neutral"


def pct_from_52w(closes: List[float]) -> float:
    hi = max(closes[-min(252, len(closes)):])
    if hi == 0: return 0.0
    return round((closes[-1] - hi) / hi * 100, 1)


def tightness(closes: List[float], w: int = 15) -> float:
    win = closes[-w:] if len(closes) >= w else closes
    if not win or max(win) == 0: return 1.0
    return (max(win) - min(win)) / max(win)


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN SCORERS
# ─────────────────────────────────────────────────────────────────────────────
def score_cup_handle(c, v) -> int:
    if len(c) < 40: return 0
    win = c[-40:]; lo_idx = int(np.argmin(win))
    if lo_idx < 5 or lo_idx > 32: return 15
    lo = win[lo_idx]; lp = max(win[:lo_idx]); rp = max(win[lo_idx:]); last = c[-1]
    depth = (lp - lo) / lp if lp > 0 else 0
    if not (0.12 <= depth <= 0.35): return 20
    recovery = (rp - lo) / (lp - lo) if lp > lo else 0
    handle_pb = (rp - last) / rp if rp > 0 else 0
    s = 45
    if recovery >= 0.85: s += 20
    if recovery >= 0.95: s += 5
    if 0.02 <= handle_pb <= 0.12: s += 15
    if last > lp * 0.97: s += 10
    if len(v) >= 20 and np.mean(v[-5:]) < np.mean(v[-20:-5]) * 0.85: s += 5
    return min(s, 95)


def score_double_bottom(c, v) -> int:
    if len(c) < 30: return 0
    win = c[-30:]; mid = len(win) // 2
    lo1 = min(win[:mid]); lo2 = min(win[mid:])
    if lo1 == 0 or lo2 == 0: return 0
    neck = max(win[mid-4:mid+4]) if mid >= 4 else max(win)
    last = c[-1]
    sim = 1 - abs(lo1 - lo2) / ((lo1 + lo2) / 2)
    if sim < 0.90: return 15
    s = 45
    if sim >= 0.97: s += 15
    elif sim >= 0.93: s += 8
    if last > neck: s += 20
    if last > lo2 * 1.05: s += 10
    if len(v) >= 10 and np.mean(v[-5:]) > np.mean(v[-20:-5]) * 1.1: s += 5
    return min(s, 92)


def score_ipo_base(c, listing_age) -> int:
    # Relaxed to 2500 days (~7 years) to include Zomato, Polycab, etc.
    if listing_age > 2500 or len(c) < 15: return 0
    win = c[-25:] if len(c) >= 25 else c
    pk = max(win); lo = min(win); last = c[-1]
    depth = (pk - lo) / pk if pk > 0 else 1.0
    if depth > 0.35: return 15
    s = 40
    if depth < 0.20: s += 15
    if depth < 0.12: s += 10
    if last > pk * 0.90: s += 15
    if last > pk * 0.97: s += 5
    if listing_age < 1000: s += 10
    if tightness(c[-15:] if len(c) >= 15 else c) < 0.10: s += 10
    return min(s, 92)


def score_momentum(c, v) -> int:
    if len(c) < 55: return 0
    e20 = ema_val(c, 20); e50 = ema_val(c, 50)
    if None in (e20, e50): return 0
    last = c[-1]; pct_hi = pct_from_52w(c); r = rsi_wilder(c)
    s = 25
    if last > e20: s += 15
    if e20 > e50: s += 15
    if pct_hi >= -5: s += 15
    elif pct_hi >= -10: s += 8
    if r and 55 <= r <= 75: s += 12
    elif r and r > 75: s += 3
    if len(v) >= 5:
        vr = vol_ratio_fn(v)
        if vr >= 1.5: s += 10
        elif vr >= 1.2: s += 5
    return min(s, 92)


def score_flat_base(c, v) -> int:
    if len(c) < 30: return 0
    win = c[-25:]; pk = max(win); lo = min(win); last = c[-1]
    band = (pk - lo) / pk if pk > 0 else 1.0
    if band > 0.15: return 20
    s = 50
    if band < 0.10: s += 15
    if band < 0.07: s += 8
    if last > (pk + lo) / 2: s += 10
    if last > pk * 0.97: s += 5
    if len(c) >= 50 and np.mean(c[-50:-25]) < lo: s += 5
    if len(v) >= 25:
        bv = np.mean(v[-25:])
        pv = np.mean(v[-50:-25]) if len(v) >= 50 else np.mean(v[:-25])
        if pv > 0 and bv < pv * 0.8: s += 7
    return min(s, 88)


# ─────────────────────────────────────────────────────────────────────────────
# ANALYZE A SINGLE STOCK
# ─────────────────────────────────────────────────────────────────────────────
def analyze_stock(yf_sym: str, disp: str, company: str, sector: str, cap: str, listing_age: int) -> Optional[dict]:
    df = fetch_ohlcv(yf_sym)
    if df is None or len(df) < 20:
        return None
    closes  = df["Close"].tolist()
    highs   = df["High"].tolist()
    lows    = df["Low"].tolist()
    volumes = df["Volume"].tolist()
    last    = float(closes[-1])
    prev    = float(closes[-2]) if len(closes) >= 2 else last
    chg     = (last - prev) / prev * 100 if prev else 0.0

    r     = rsi_wilder(closes) or 50.0
    vr    = vol_ratio_fn(volumes)
    trend = trend_signal(closes)
    pcthi = pct_from_52w(closes)
    mbull = macd_bullish(closes)
    tight = tightness(closes)

    scores = {
        "cup":  score_cup_handle(closes, volumes),
        "dbl":  score_double_bottom(closes, volumes),
        "ipo":  score_ipo_base(closes, listing_age),
        "mom":  score_momentum(closes, volumes),
        "flat": score_flat_base(closes, volumes),
    }
    return {
        "symbol": disp, "company": company, "sector": sector, "cap": cap,
        "price": float(round(last, 2)), "change_pct": float(round(chg, 2)),
        "rsi": float(round(r, 1)), "vol_ratio": float(round(vr, 2)),
        "trend": str(trend), "pct_from_52w_high": float(pcthi),
        "macd_bull": bool(mbull), "tightness": float(round(tight, 3)),
        "scores": {k: int(v) for k, v in scores.items()}, "listing_age_days": int(listing_age),
    }


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND CACHE
# ─────────────────────────────────────────────────────────────────────────────
_lock = threading.Lock()
_cache: List[dict] = []
_cache_ts: float = 0.0
_building = False
CACHE_TTL = 300


def _build():
    global _cache, _cache_ts, _building
    log.info(f"Building universe cache for {len(UNIVERSE)} stocks…")
    # Prime Yahoo session cookie first
    try: _session.get("https://finance.yahoo.com/", timeout=10)
    except Exception: pass
    get_crumb()

    results = []
    for entry in UNIVERSE:
        try:
            r = analyze_stock(*entry)
            if r:
                results.append(r)
                log.info(f"  ✓ {entry[1]} ({len(results)} done)")
        except Exception as e:
            log.warning(f"  ✗ {entry[1]}: {e}")
    with _lock:
        if results:  # only update if we got data
            _cache = results
            _cache_ts = time.time()
        _building = False
    log.info(f"Cache complete: {len(results)}/{len(UNIVERSE)} stocks")


def trigger_refresh():
    global _building
    with _lock:
        if _building: return
        _building = True
    threading.Thread(target=_build, daemon=True).start()


def get_cache():
    with _lock: return list(_cache)
def cache_age():
    with _lock: return time.time() - _cache_ts if _cache_ts else float("inf")
def cache_count():
    with _lock: return len(_cache)


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY CONFIG
# ─────────────────────────────────────────────────────────────────────────────
STRATEGY_IDS = ["cup", "dbl", "ipo", "mom", "flat"]
STRATEGY_META = {
    "cup":  {"name": "Cup & Handle",      "rr": 2.5, "tgt_pct": 0.17, "stop_pct": 0.07},
    "dbl":  {"name": "Double Bottom",     "rr": 2.2, "tgt_pct": 0.13, "stop_pct": 0.055},
    "ipo":  {"name": "IPO Base",          "rr": 2.0, "tgt_pct": 0.11, "stop_pct": 0.05},
    "mom":  {"name": "Momentum Breakout", "rr": 2.5, "tgt_pct": 0.14, "stop_pct": 0.06},
    "flat": {"name": "Flat Base",         "rr": 1.8, "tgt_pct": 0.10, "stop_pct": 0.055},
}


def calc_levels(price, sid):
    m = STRATEGY_META[sid]
    return {"entry": round(price,2), "target": round(price*(1+m["tgt_pct"]),2),
            "stop": round(price*(1-m["stop_pct"]),2),
            "tgt_pct": round(m["tgt_pct"]*100,1), "stop_pct": round(m["stop_pct"]*100,1)}


def build_reasoning(s: dict, sid: str) -> List[str]:
    r = []; m = STRATEGY_META[sid]
    rv = s["rsi"]; vr = s["vol_ratio"]; trend = s["trend"]
    phi = s["pct_from_52w_high"]; mb = s["macd_bull"]
    if sid == "cup":
        r.append(f"<b>Cup & Handle</b> — rounded base with handle pullback near pivot")
        r.append(f"Fit score <b>{s['scores']['cup']}/100</b>")
        if vr >= 1.5: r.append(f"Volume <b>{vr:.1f}×</b> 20-day avg — strong accumulation")
        elif vr >= 1.2: r.append(f"Volume <b>{vr:.1f}×</b> — healthy buying interest")
        if 55 <= rv <= 75: r.append(f"RSI (Wilder) <b>{rv}</b> — power zone, upside room")
        if trend == "bullish": r.append("Trend: <b>Bullish</b> — Price > EMA20 > EMA50")
        if mb: r.append("MACD <b>above signal</b> — momentum expanding")
        if phi >= -5: r.append(f"<b>{abs(phi):.1f}%</b> from 52-week high — nearing breakout zone")
        r.append(f"Target: +{int(m['tgt_pct']*100)}% · Stop: -{int(m['stop_pct']*100)}% · R/R: <b>{m['rr']}×</b>")
    elif sid == "dbl":
        r.append(f"<b>Double Bottom (W)</b> — two lows at same support")
        r.append(f"Fit score <b>{s['scores']['dbl']}/100</b>")
        if rv < 45: r.append(f"RSI <b>{rv}</b> — bullish divergence potential")
        else: r.append(f"RSI <b>{rv}</b> — momentum turning higher")
        if vr >= 1.3: r.append(f"Volume <b>{vr:.1f}×</b> — neckline break validated")
        if mb: r.append("MACD crossover <b>bullish</b>")
        if trend == "bullish": r.append("Primary trend: <b>Bullish</b>")
        r.append(f"Target: +{int(m['tgt_pct']*100)}% · Stop: -{int(m['stop_pct']*100)}% · R/R: <b>{m['rr']}×</b>")
    elif sid == "ipo":
        r.append(f"<b>First IPO Base</b> — institutional accumulation post listing")
        r.append(f"Listed ~{s['listing_age_days']} days ago")
        r.append(f"Fit score <b>{s['scores']['ipo']}/100</b>")
        if trend == "bullish": r.append("Primary uptrend intact — first bases deliver explosive moves")
        if s["tightness"] < 0.10: r.append(f"Range: <b>{s['tightness']*100:.1f}%</b> — very tight base")
        r.append(f"RSI <b>{rv}</b> · Target: +{int(m['tgt_pct']*100)}% · R/R: <b>{m['rr']}×</b>")
    elif sid == "mom":
        r.append(f"<b>Momentum Breakout</b> — clearing multi-month resistance")
        r.append(f"Fit score <b>{s['scores']['mom']}/100</b>")
        r.append(f"{'At 52-week high ▲' if phi >= -2 else f'{abs(phi):.1f}% from 52-week high'}")
        if 55 <= rv <= 75: r.append(f"RSI <b>{rv}</b> — momentum power zone (55–75)")
        elif rv > 75: r.append(f"RSI <b>{rv}</b> — extended; pullback to EMA20 ideal entry")
        if vr >= 1.5: r.append(f"Volume surge <b>{vr:.1f}×</b> — institutional conviction")
        if mb: r.append("MACD <b>bullish</b> — histogram expanding")
        r.append(f"Target: +{int(m['tgt_pct']*100)}% · Trailing stop · R/R: <b>{m['rr']}×</b>")
    else:
        r.append(f"<b>Flat Base / Darvas Box</b> — tight consolidation on prior rally")
        r.append(f"Fit score <b>{s['scores']['flat']}/100</b> · Range: <b>{s['tightness']*100:.1f}%</b>")
        if vr < 0.9: r.append(f"Volume drying up (<b>{vr:.1f}×</b>) — healthy base building")
        elif vr >= 1.3: r.append(f"Volume <b>{vr:.1f}×</b> — quiet accumulation visible")
        if trend == "bullish": r.append("Built on <b>bullish</b> EMAs — constructive")
        if mb: r.append("MACD positive — underlying momentum intact")
        r.append(f"Target: +{int(m['tgt_pct']*100)}% · Stop: box floor · R/R: <b>{m['rr']}×</b>")
    return r


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="SWING Terminal", version="4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.on_event("startup")
async def startup():
    log.info("Startup — triggering background cache build")
    trigger_refresh()


@app.get("/")
async def root():
    idx = FRONTEND_DIR / "index.html"
    return FileResponse(str(idx)) if idx.exists() else {"version": "4.0"}


@app.get("/api/health")
async def health():
    return {"ok": True, "universe_cached": cache_count(),
            "cache_age_s": round(cache_age(), 0) if cache_count() > 0 else None, "building": _building}


@app.get("/api/status")
async def status():
    cnt = cache_count()
    return {"stocks_cached": cnt, "cache_age_s": round(cache_age(), 0) if cnt > 0 else None,
            "building": _building, "ready": cnt > 0}


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
    import traceback
    if params.strategy not in STRATEGY_IDS:
        raise HTTPException(400, f"Unknown strategy: {params.strategy}")
    for _ in range(13):
        if cache_count() > 0: break
        await asyncio.sleep(2)
    stocks = get_cache()
    if not stocks:
        trigger_refresh()
        raise HTTPException(503, "Data loading — try again in 30s.")
    
    meta = STRATEGY_META[params.strategy]
    results = []
    try:
        for s in stocks:
            score = s["scores"].get(params.strategy, 0)
            if score < max(params.min_score, 20): continue
            if params.cap != "any" and s["cap"] != params.cap: continue
            if params.sector != "any" and s["sector"] != params.sector: continue
            if params.trend != "any" and s["trend"] != params.trend: continue
            results.append({**s, "fit_score": score, "strategy_meta": meta,
                            "levels": calc_levels(s["price"], params.strategy),
                            "reasoning": build_reasoning(s, params.strategy)})
        results.sort(key=lambda x: x["fit_score"], reverse=True)
        return json_safe({"strategy": params.strategy, "count": len(results),
                         "total_analyzed": len(stocks), "results": results[:30]})
    except Exception as e:
        log.error(f"Scan crash: {traceback.format_exc()}")
        raise HTTPException(500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
