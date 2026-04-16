# SWING Terminal — Live NSE Pattern Scanner

A full-stack swing-trading dashboard that scrapes NSE India directly for
live prices and scores stocks against 5 institutional swing-trading
base patterns: **Cup & Handle, Double Bottom, IPO Base, Momentum
Breakout, Flat Base**.

- **Backend**: FastAPI (Python) — scrapes NSE, computes RSI/EMA/trend,
  runs pattern detection.
- **Frontend**: Single-page static HTML served by the same backend —
  no build step, no CORS headaches.
- **Deploy**: One-click to Render.com free tier.

## Quick local run

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://localhost:8000

---

## 🚀 Deploy to Render (free, ~5 min)

### Step 1 — Push this folder to GitHub

```bash
cd swing-terminal
git init
git add .
git commit -m "Initial commit"
git branch -M main
# Create a new empty repo on github.com first, then:
git remote add origin https://github.com/YOUR_USERNAME/swing-terminal.git
git push -u origin main
```

### Step 2 — Connect Render

1. Go to **https://render.com** and sign up (free, use GitHub auth).
2. Dashboard → **New +** → **Blueprint**.
3. Connect the GitHub repo you just pushed.
4. Render auto-detects `render.yaml` and proposes the service. Click
   **Apply**.
5. Wait ~3-5 min for first build.
6. You'll get a URL like `https://swing-terminal-xxxx.onrender.com`.

That's it. The URL is live, public, and auto-deploys every time you push
to `main`.

### Notes on the free plan

- Render's free tier **spins down after 15 min of inactivity**. First
  request after idle wakes it up (takes ~30 sec).
- 750 instance-hours/month (more than enough).
- For an always-on service, upgrade to $7/mo Starter.

---

## Project structure

```
swing-terminal/
├── backend/
│   ├── main.py              # FastAPI app + NSE scraper + patterns
│   └── requirements.txt
├── frontend/
│   └── index.html           # Single-page UI (served by backend)
├── render.yaml              # Render deploy config
├── .gitignore
└── README.md
```

## API routes

| Route               | Method | Purpose                             |
|---------------------|--------|-------------------------------------|
| `/`                 | GET    | Serves the frontend                 |
| `/api/health`       | GET    | Healthcheck                         |
| `/api/strategies`   | GET    | List of 5 strategies with metadata  |
| `/api/scan`         | POST   | Run a pattern scan with filters     |
| `/api/quote/{sym}`  | GET    | Live NSE quote for a single symbol  |

## Scan payload

```json
{
  "strategy": "cup",
  "cap": "any|large|mid|small",
  "sector": "any|Information Technology|Banking & Financials|...",
  "min_score": 0,
  "min_rr": 0,
  "trend": "any|bullish|neutral|bearish",
  "volume_confirmed": false
}
```

## Caveats

- **First scan takes 30-60 sec** — the server fetches ~65 NSE quotes
  and historical series the first time, then caches for 5 min.
- **NSE occasionally rate-limits** anonymous scrapers. If a scan fails,
  wait 30 sec and retry. The cookie/session layer handles most issues
  but NSE's API is not officially public.
- **Educational use only.** Pattern scores are heuristic
  approximations, not broker-grade technical analysis. Verify every
  trade on your own platform before entering.

## License

MIT — do whatever you want with this.
