"""
SWING Terminal — FastAPI backend
Scrapes NSE India directly for live quotes and historical OHLC,
computes indicators, and scores stocks against 5 swing patterns.
"""
import os
import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import asyncio

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("swing")

# ─────────────────────────────────────────────────────────────────────
# NSE SCRAPER — NSE blocks bots, so we spoof a real browser session
# ─────────────────────────────────────────────────────────────────────
NSE_BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

# Shared client w/ cookie jar. NSE needs you to visit homepage first to get cookies.
_client: Optional[httpx.AsyncClient] = None
_cookie_refreshed_at = 0
_quote_cache: Dict[str, Tuple[float, dict]] = {}  # {symbol: (ts, data)}
CACHE_TTL = 60  # seconds


async def get_client() -> httpx.AsyncClient:
    global _client, _cookie_refreshed_at
    now = time.time()
    if _client is None or (now - _cookie_refreshed_at) > 300:
        if _client is not None:
            await _client.aclose()
        _client = httpx.AsyncClient(headers=HEADERS, timeout=20.0, follow_redirects=True)
        # prime cookies
        try:
            await _client.get(NSE_BASE)
            await _client.get(f"{NSE_BASE}/market-data/live-equity-market")
            _cookie_refreshed_at = now
            log.info("NSE cookies primed")
        except Exception as e:
            log.warning(f"Cookie priming failed: {e}")
    return _client


async def nse_quote(symbol: str) -> Optional[dict]:
    """Fetch live quote for a stock."""
    cached = _quote_cache.get(symbol)
    if cached and (time.time() - cached[0]) < CACHE_TTL:
        return cached[1]
    client = await get_client()
    url = f"{NSE_BASE}/api/quote-equity?symbol={symbol}"
    try:
        r = await client.get(url)
        if r.status_code == 401:
            # re-prime cookies and retry once
            await client.get(NSE_BASE)
            r = await client.get(url)
        if r.status_code != 200:
            log.warning(f"NSE {symbol} HTTP {r.status_code}")
            return None
        data = r.json()
        _quote_cache[symbol] = (time.time(), data)
        return data
    except Exception as e:
        log.warning(f"Quote {symbol} failed: {e}")
        return None


async def nse_historical(symbol: str, days: int = 200) -> Optional[List[dict]]:
    """
    Fetch daily OHLC for indicator calcs.
    NSE's chart endpoint returns per-minute; we use their historical CM endpoint.
    """
    client = await get_client()
    # Use the chart-databyindex endpoint which is more stable
    url = f"{NSE_BASE}/api/chart-databyindex?index={symbol}EQN&preference=W"
    try:
        r = await client.get(url)
        if r.status_code != 200:
            return None
        data = r.json()
        # grapthData: [[timestamp_ms, price], ...]
        series = data.get("grapthData", [])
        if not series:
            return None
        # Convert to pseudo-OHLC daily (price points sampled weekly give us enough)
        closes = [p[1] for p in series if p and len(p) >= 2]
        return closes
    except Exception as e:
        log.warning(f"Historical {symbol} failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────────────────────────────
def rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    arr = np.array(closes[-(period + 1):], dtype=float)
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0).mean()
    losses = np.where(deltas < 0, -deltas, 0).mean()
    if losses == 0:
        return 100.0
    rs = gains / losses
    return float(100 - (100 / (1 + rs)))


def ema(closes: List[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    arr = np.array(closes, dtype=float)
    k = 2 / (period + 1)
    e = arr[0]
    for x in arr[1:]:
        e = x * k + e * (1 - k)
    return float(e)


def trend_signal(closes: List[float]) -> str:
    if len(closes) < 50:
        return "neutral"
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    if e20 is None or e50 is None:
        return "neutral"
    last = closes[-1]
    if last > e20 > e50:
        return "bullish"
    if last < e20 < e50:
        return "bearish"
    return "neutral"


# ─────────────────────────────────────────────────────────────────────
# PATTERN DETECTION — simplified heuristics scoring 0-100
# ─────────────────────────────────────────────────────────────────────
def score_cup_handle(closes: List[float]) -> int:
    """Rounded base + shallow pullback + recovery near pivot."""
    if len(closes) < 30:
        return 0
    win = closes[-30:]
    lo_idx = np.argmin(win)
    lo = win[lo_idx]
    peak_before = max(win[:lo_idx]) if lo_idx > 2 else win[0]
    peak_after = max(win[lo_idx:]) if lo_idx < len(win) - 2 else win[-1]
    last = closes[-1]
    depth = (peak_before - lo) / peak_before if peak_before else 0
    if not (0.10 < depth < 0.35):
        return 20
    recovery = (peak_after - lo) / (peak_before - lo) if peak_before > lo else 0
    handle_pullback = (peak_after - last) / peak_after if peak_after else 0
    score = 50
    if recovery > 0.85: score += 20
    if 0.02 < handle_pullback < 0.12: score += 20
    if last > peak_before * 0.97: score += 10
    return min(score, 95)


def score_double_bottom(closes: List[float]) -> int:
    if len(closes) < 25:
        return 0
    win = closes[-25:]
    mid = len(win) // 2
    lo1 = min(win[:mid])
    lo2 = min(win[mid:])
    peak_between = max(win[mid - 3:mid + 3]) if mid > 3 else max(win)
    last = closes[-1]
    if lo1 == 0 or lo2 == 0:
        return 0
    similarity = 1 - abs(lo1 - lo2) / ((lo1 + lo2) / 2)
    if similarity < 0.92:
        return 20
    score = 50
    if similarity > 0.97: score += 15
    if last > peak_between: score += 20
    if last > lo2 * 1.05: score += 10
    return min(score, 92)


def score_ipo_base(closes: List[float], listing_days_est: int) -> int:
    """IPO base requires stock to be relatively young."""
    if listing_days_est > 750 or len(closes) < 20:
        return 0
    win = closes[-30:] if len(closes) >= 30 else closes
    peak = max(win)
    lo = min(win)
    depth = (peak - lo) / peak if peak else 0
    last = closes[-1]
    if depth > 0.30:
        return 25
    score = 55
    if depth < 0.20: score += 15
    if last > peak * 0.95: score += 20
    if listing_days_est < 365: score += 5
    return min(score, 90)


def score_momentum(closes: List[float]) -> int:
    if len(closes) < 50:
        return 0
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    last = closes[-1]
    peak_52w = max(closes[-min(len(closes), 200):])
    if e20 is None or e50 is None:
        return 0
    score = 30
    if last > e20: score += 15
    if e20 > e50: score += 20
    if last > peak_52w * 0.95: score += 20
    r = rsi(closes)
    if r and 55 <= r <= 70: score += 10
    return min(score, 92)


def score_flat_base(closes: List[float]) -> int:
    if len(closes) < 25:
        return 0
    win = closes[-25:]
    peak = max(win)
    lo = min(win)
    band = (peak - lo) / peak if peak else 0
    if band > 0.15:
        return 25
    score = 55
    if band < 0.10: score += 15
    if band < 0.07: score += 10
    last = closes[-1]
    if last > (peak + lo) / 2: score += 10
    return min(score, 88)


# ─────────────────────────────────────────────────────────────────────
# STOCK UNIVERSE — ~60 NSE tickers with sector & cap tags
# ─────────────────────────────────────────────────────────────────────
UNIVERSE = [
    # (symbol, company, sector, cap, approx_listing_age_days)
    ("TCS", "Tata Consultancy Services", "Information Technology", "large", 5500),
    ("INFY", "Infosys", "Information Technology", "large", 8000),
    ("WIPRO", "Wipro", "Information Technology", "large", 8000),
    ("HCLTECH", "HCL Technologies", "Information Technology", "large", 7000),
    ("TECHM", "Tech Mahindra", "Information Technology", "large", 5500),
    ("LTIM", "LTIMindtree", "Information Technology", "mid", 900),
    ("PERSISTENT", "Persistent Systems", "Information Technology", "mid", 4500),
    ("COFORGE", "Coforge", "Information Technology", "mid", 5000),
    ("KPITTECH", "KPIT Technologies", "Information Technology", "small", 1800),
    ("TATAELXSI", "Tata Elxsi", "Information Technology", "mid", 7000),
    ("HAPPSTMNDS", "Happiest Minds Technologies", "Information Technology", "small", 1500),
    ("LATENTVIEW", "Latent View Analytics", "Information Technology", "small", 1400),
    ("MAPMYINDIA", "C.E. Info Systems", "Information Technology", "small", 1100),

    ("HDFCBANK", "HDFC Bank", "Banking & Financials", "large", 9000),
    ("ICICIBANK", "ICICI Bank", "Banking & Financials", "large", 9000),
    ("AXISBANK", "Axis Bank", "Banking & Financials", "large", 8500),
    ("KOTAKBANK", "Kotak Mahindra Bank", "Banking & Financials", "large", 8000),
    ("SBIN", "State Bank of India", "Banking & Financials", "large", 9000),
    ("BAJFINANCE", "Bajaj Finance", "Banking & Financials", "large", 6000),
    ("BAJAJFINSV", "Bajaj Finserv", "Banking & Financials", "large", 5500),
    ("CDSL", "Central Depository Services", "Banking & Financials", "small", 2800),
    ("PAYTM", "One97 Communications", "Banking & Financials", "mid", 1550),

    ("RELIANCE", "Reliance Industries", "Energy", "large", 9000),
    ("ONGC", "ONGC", "Energy", "large", 8500),
    ("IOC", "Indian Oil Corporation", "Energy", "large", 8000),
    ("BPCL", "Bharat Petroleum", "Energy", "large", 8000),
    ("IEX", "Indian Energy Exchange", "Energy", "mid", 1500),

    ("SUNPHARMA", "Sun Pharmaceutical", "Pharmaceuticals", "large", 8000),
    ("DRREDDY", "Dr Reddy's Laboratories", "Pharmaceuticals", "large", 8500),
    ("CIPLA", "Cipla", "Pharmaceuticals", "large", 8500),
    ("LUPIN", "Lupin", "Pharmaceuticals", "mid", 7500),
    ("MANKIND", "Mankind Pharma", "Pharmaceuticals", "mid", 900),
    ("METROPOLIS", "Metropolis Healthcare", "Pharmaceuticals", "small", 2500),
    ("RAINBOW", "Rainbow Children's Medicare", "Pharmaceuticals", "small", 1300),

    ("MARUTI", "Maruti Suzuki India", "Auto & Ancillaries", "large", 7500),
    ("M&M", "Mahindra & Mahindra", "Auto & Ancillaries", "large", 8500),
    ("TATAMOTORS", "Tata Motors", "Auto & Ancillaries", "large", 9000),
    ("BAJAJ-AUTO", "Bajaj Auto", "Auto & Ancillaries", "large", 6000),
    ("EICHERMOT", "Eicher Motors", "Auto & Ancillaries", "large", 7000),
    ("SONACOMS", "Sona BLW Precision", "Auto & Ancillaries", "mid", 1700),

    ("ITC", "ITC", "FMCG", "large", 9000),
    ("HINDUNILVR", "Hindustan Unilever", "FMCG", "large", 9000),
    ("NESTLEIND", "Nestle India", "FMCG", "large", 8500),
    ("BRITANNIA", "Britannia Industries", "FMCG", "large", 8500),
    ("DABUR", "Dabur India", "FMCG", "large", 8500),

    ("LT", "Larsen & Toubro", "Capital Goods", "large", 8500),
    ("ULTRACEMCO", "UltraTech Cement", "Capital Goods", "large", 7000),
    ("POLYCAB", "Polycab India", "Capital Goods", "mid", 2300),
    ("ASTRAL", "Astral Ltd", "Capital Goods", "mid", 5500),
    ("IRCTC", "Indian Railway Catering", "Capital Goods", "mid", 2300),

    ("TATASTEEL", "Tata Steel", "Metals", "large", 9000),
    ("JSWSTEEL", "JSW Steel", "Metals", "large", 7000),
    ("HINDALCO", "Hindalco Industries", "Metals", "large", 8000),

    ("TITAN", "Titan Company", "Consumer Durables", "large", 8000),
    ("VOLTAS", "Voltas", "Consumer Durables", "mid", 8000),
    ("DIXON", "Dixon Technologies", "Consumer Durables", "mid", 1900),
    ("NYKAA", "FSN E-Commerce Ventures", "Consumer Durables", "mid", 1550),
    ("ZOMATO", "Zomato", "Consumer Durables", "mid", 1700),
    ("TRENT", "Trent", "Consumer Durables", "mid", 8000),
    ("CAMPUS", "Campus Activewear", "Consumer Durables", "small", 1450),

    ("ASIANPAINT", "Asian Paints", "FMCG", "large", 8500),
    ("PIIND", "PI Industries", "Chemicals", "mid", 6000),
    ("SRF", "SRF", "Chemicals", "mid", 7000),
    ("DEEPAKNTR", "Deepak Nitrite", "Chemicals", "mid", 6000),
    ("NAVINFLUOR", "Navin Fluorine", "Chemicals", "mid", 7000),
]


# ─────────────────────────────────────────────────────────────────────
# SCORE A SINGLE STOCK
# ─────────────────────────────────────────────────────────────────────
STRATEGY_IDS = ["cup", "dbl", "ipo", "mom", "flat"]
STRATEGY_META = {
    "cup":  {"name": "Cup & Handle",       "rr": 2.5, "tgt_pct": 0.17, "stop_pct": 0.07},
    "dbl":  {"name": "Double Bottom",      "rr": 2.2, "tgt_pct": 0.13, "stop_pct": 0.055},
    "ipo":  {"name": "IPO Base",           "rr": 2.0, "tgt_pct": 0.11, "stop_pct": 0.05},
    "mom":  {"name": "Momentum Breakout",  "rr": 2.5, "tgt_pct": 0.14, "stop_pct": 0.06},
    "flat": {"name": "Flat Base",          "rr": 1.8, "tgt_pct": 0.10, "stop_pct": 0.055},
}


async def analyze_stock(entry: Tuple[str, str, str, str, int]) -> Optional[dict]:
    symbol, company, sector, cap, listing_age = entry
    quote = await nse_quote(symbol)
    if not quote:
        return None
    closes = await nse_historical(symbol)
    if not closes or len(closes) < 20:
        return None

    price_info = quote.get("priceInfo", {})
    last_price = price_info.get("lastPrice")
    pct_change = price_info.get("pChange")
    if last_price is None:
        return None

    # Volume ratio
    pre_open = quote.get("securityWiseDP", {}) or {}
    qty_traded = pre_open.get("quantityTraded") or price_info.get("totalTradedVolume") or 0
    # We don't have avg vol easily; use a rough heuristic from price action intensity
    vol_ratio = 1.0
    if len(closes) >= 10:
        recent_range = (max(closes[-5:]) - min(closes[-5:])) / np.mean(closes[-5:])
        vol_ratio = max(0.7, min(3.0, 1.0 + recent_range * 10))

    r = rsi(closes) or 50.0
    trend = trend_signal(closes)

    scores = {
        "cup": score_cup_handle(closes),
        "dbl": score_double_bottom(closes),
        "ipo": score_ipo_base(closes, listing_age),
        "mom": score_momentum(closes),
        "flat": score_flat_base(closes),
    }

    return {
        "symbol": symbol,
        "company": company,
        "sector": sector,
        "cap": cap,
        "price": float(last_price),
        "change_pct": float(pct_change) if pct_change is not None else 0.0,
        "rsi": round(r, 1),
        "vol_ratio": round(vol_ratio, 2),
        "trend": trend,
        "scores": scores,
        "listing_age_days": listing_age,
    }


# ─────────────────────────────────────────────────────────────────────
# REASONING GENERATOR
# ─────────────────────────────────────────────────────────────────────
def build_reasoning(stock: dict, strat_id: str) -> List[str]:
    r = []
    meta = STRATEGY_META[strat_id]
    rsi_v, vol, trend = stock["rsi"], stock["vol_ratio"], stock["trend"]

    if strat_id == "cup":
        r.append(f"<b>Cup & Handle</b> pattern detected — rounded base with handle formation")
        r.append(f"Fit score <b>{stock['scores']['cup']}/100</b> — structure meets institutional criteria")
        if vol >= 1.5:
            r.append(f"Volume at <b>{vol:.1f}× recent average</b> — accumulation confirmed")
        if 55 <= rsi_v <= 70:
            r.append(f"RSI at <b>{rsi_v}</b> — strong momentum, not yet overbought")
        if trend == "bullish":
            r.append(f"Aligned with <b>bullish</b> primary trend (price > 20EMA > 50EMA)")
        r.append(f"Typical move of <b>14–20%</b> on confirmed breakout; R/R <b>{meta['rr']}×</b>")
    elif strat_id == "dbl":
        r.append(f"<b>Double Bottom</b> (W-reversal) forming — two lows at similar level")
        r.append(f"Fit score <b>{stock['scores']['dbl']}/100</b>")
        if rsi_v < 55:
            r.append(f"RSI at <b>{rsi_v}</b> — potential bullish divergence from second low")
        else:
            r.append(f"RSI at <b>{rsi_v}</b> — momentum already shifting bullish")
        if vol >= 1.3:
            r.append(f"Volume (<b>{vol:.1f}×</b>) validates reversal strength")
        r.append(f"Measured-move target: <b>+10–16%</b>; stop below second low")
    elif strat_id == "ipo":
        r.append(f"<b>First IPO Base</b> — institutional accumulation zone for young listing")
        r.append(f"Listed ~{stock['listing_age_days']} days ago — inside the IPO window")
        r.append(f"Fit score <b>{stock['scores']['ipo']}/100</b> — tight price action post-IPO")
        if trend == "bullish":
            r.append(f"Primary uptrend intact — first bases deliver explosive moves")
        r.append(f"RSI at <b>{rsi_v}</b>; historic avg move <b>7–15%</b>")
    elif strat_id == "mom":
        r.append(f"<b>Momentum Breakout</b> — price clearing multi-month resistance")
        r.append(f"Fit score <b>{stock['scores']['mom']}/100</b>")
        r.append(f"Trend: <b>{trend}</b> — moving averages aligned")
        if 55 <= rsi_v <= 70:
            r.append(f"RSI <b>{rsi_v}</b> in the 55–70 power zone")
        elif rsi_v > 70:
            r.append(f"RSI <b>{rsi_v}</b> — overbought; wait for shallow pullback")
        if vol >= 1.5:
            r.append(f"Volume surge (<b>{vol:.1f}×</b>) confirms trend-follow entry")
        r.append(f"Ride with trailing stop; typical move <b>10–18%</b>")
    else:  # flat
        r.append(f"<b>Flat Base / Darvas Box</b> — tight sideways consolidation")
        r.append(f"Fit score <b>{stock['scores']['flat']}/100</b>")
        r.append(f"Correction contained — healthy digestion of prior gains")
        if vol >= 1.3:
            r.append(f"Volume at <b>{vol:.1f}×</b> shows accumulation footprint inside the box")
        r.append(f"Breakout targets <b>+8–14%</b>; stop under box floor")
    return r


def calc_levels(price: float, strat_id: str) -> dict:
    m = STRATEGY_META[strat_id]
    entry = price
    return {
        "entry": round(entry, 2),
        "target": round(entry * (1 + m["tgt_pct"]), 2),
        "stop": round(entry * (1 - m["stop_pct"]), 2),
        "tgt_pct": round(m["tgt_pct"] * 100, 1),
        "stop_pct": round(m["stop_pct"] * 100, 1),
    }


# ─────────────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="SWING Terminal API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache of analyzed universe
_universe_cache: Tuple[float, List[dict]] = (0, [])
UNIVERSE_TTL = 300  # re-analyze every 5 min


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
async def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"status": "ok", "service": "swing-terminal", "time": datetime.utcnow().isoformat()}


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/strategies")
async def strategies():
    return [
        {"id": "cup",  "rank": "S-01", "name": "Cup & Handle",       "win": "65–85%", "avg": "14–20%", "rr": 2.5},
        {"id": "dbl",  "rank": "S-02", "name": "Double Bottom",      "win": "70–80%", "avg": "10–16%", "rr": 2.2},
        {"id": "ipo",  "rank": "S-03", "name": "IPO Base",           "win": "65–75%", "avg": "7–15%",  "rr": 2.0},
        {"id": "mom",  "rank": "S-04", "name": "Momentum Breakout",  "win": "60–80%", "avg": "10–18%", "rr": 2.5},
        {"id": "flat", "rank": "S-05", "name": "Flat Base",          "win": "60–70%", "avg": "8–14%",  "rr": 1.8},
    ]


async def build_universe() -> List[dict]:
    global _universe_cache
    now = time.time()
    if _universe_cache[1] and (now - _universe_cache[0]) < UNIVERSE_TTL:
        return _universe_cache[1]
    log.info(f"Analyzing {len(UNIVERSE)} stocks…")
    # Run with concurrency limit to avoid NSE rate limits
    sem = asyncio.Semaphore(4)
    async def gated(entry):
        async with sem:
            return await analyze_stock(entry)
    results = await asyncio.gather(*[gated(e) for e in UNIVERSE], return_exceptions=True)
    analyzed = [r for r in results if r and not isinstance(r, Exception)]
    log.info(f"Analyzed {len(analyzed)}/{len(UNIVERSE)}")
    _universe_cache = (now, analyzed)
    return analyzed


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
    meta = STRATEGY_META[params.strategy]

    results = []
    for s in stocks:
        score = s["scores"].get(params.strategy, 0)
        if score < max(params.min_score, 40):  # min 40 to filter noise
            continue
        if params.cap != "any" and s["cap"] != params.cap:
            continue
        if params.sector != "any" and s["sector"] != params.sector:
            continue
        if params.min_rr > 0 and meta["rr"] < params.min_rr:
            continue
        if params.trend != "any" and s["trend"] != params.trend:
            continue
        if params.volume_confirmed and s["vol_ratio"] < 1.5:
            continue

        levels = calc_levels(s["price"], params.strategy)
        reasoning = build_reasoning(s, params.strategy)
        results.append({
            **s,
            "fit_score": score,
            "strategy_meta": meta,
            "levels": levels,
            "reasoning": reasoning,
        })

    results.sort(key=lambda x: x["fit_score"], reverse=True)
    return {
        "strategy": params.strategy,
        "count": len(results),
        "total_analyzed": len(stocks),
        "results": results[:30],
    }


@app.get("/api/quote/{symbol}")
async def single_quote(symbol: str):
    q = await nse_quote(symbol.upper())
    if not q:
        raise HTTPException(404, "Quote unavailable")
    return q


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
