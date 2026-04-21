import pyttsx3
import os
import time

# Output directory
OUT = r"C:\Users\akyan\OneDrive\Desktop\Anand\Stock Screener\files\swing-terminal\demo_assets"
os.makedirs(OUT, exist_ok=True)

engine = pyttsx3.init()

# Use the best available Windows voice (Microsoft David or Zira or Heera)
voices = engine.getProperty('voices')
print("Available voices:")
for i, v in enumerate(voices):
    print(f"  [{i}] {v.name} | {v.id}")

# Pick a good voice
selected = None
for v in voices:
    if 'David' in v.name or 'Mark' in v.name or 'Guy' in v.name or 'George' in v.name:
        selected = v
        break
if not selected and len(voices) > 0:
    selected = voices[0]

if selected:
    engine.setProperty('voice', selected.id)
    print(f"\nUsing voice: {selected.name}")

engine.setProperty('rate', 155)   # words per minute - clear and professional
engine.setProperty('volume', 1.0)

# Narration segments timed to match demo sections
segments = [
    ("00_intro",
     "Welcome to SWING — the Neural Pattern Extraction Terminal. "
     "This is a real-time stock screening dashboard, purpose-built for NSE swing traders. "
     "The entire interface operates on live market data, powered by Yahoo Finance and a proprietary "
     "heuristic scoring engine. Let me walk you through every feature."),

    ("01_header",
     "At the top, you'll see the live status hub. "
     "The Market indicator shows whether NSE is currently in an active session or on standby. "
     "The Core status confirms that our neural cache is verified and populated. "
     "And the real-time clock keeps you synchronized across every scan cycle."),

    ("02_strategies",
     "On the left side panel, you have five heuristic profiles — each representing a distinct technical pattern strategy. "
     "Strategy S-01, Cup and Handle, offers a win rate of 65 to 85 percent, with an average move of 14 to 20 percent "
     "and a risk-to-reward ratio of 2.5. "
     "Strategy S-02, Double Bottom, gives 70 to 80 percent win rate with a 2.2 risk-reward. "
     "S-03 is the IPO Base pattern, ideal for catching institutional accumulation in recently listed stocks. "
     "S-04 covers Momentum Breakout for trend-acceleration plays, "
     "and S-05 is the Flat Base — a tight consolidation setup favored by institutional buyers. "
     "Simply click any strategy card to activate it. Notice the neon green border and the glow effect on selection."),

    ("03_filters",
     "The right panel is your configuration center. "
     "You have four powerful filters. "
     "First — Market Universe — lets you target the full Global Universe, or narrow to Large-cap institutional stocks, "
     "Mid-cap growth plays, or Small-cap speculative setups. "
     "Second — Sector Segment — allows you to focus on a specific industry like Information Technology, "
     "Banking and Financials, Pharmaceuticals, FMCG, and more. "
     "Third — Intelligence Grade — controls the minimum fit score threshold. "
     "Setting this to Elite Optima filters only stocks scoring 80 or above on the pattern confidence index. "
     "And fourth — Trend Orientation — lets you filter for bullish, neutral, or biaxial trends."),

    ("04_scan",
     "Once configured, hit Execute Live Scan. "
     "The system simultaneously queries all 55 stocks in the NSE universe, "
     "runs the heuristic scoring algorithm, and returns matches in real time. "
     "For Cup and Handle, we see 52 entities match — including Tech Mahindra, CDSL, Asian Paints, Tata Steel, and Hindalco. "
     "Each result is ranked by fit score, highest first."),

    ("05_cards",
     "Each entity card shows a complete trading snapshot. "
     "At the top — the ticker symbol, company name, current price, and live percentage change. "
     "Below that, color-coded badges identify the detected pattern type, the sector, and market cap classification. "
     "The metric grid gives you six key datapoints: RSI signal, Volume density relative to average, "
     "proximity to the 52-week high, Momentum direction from MACD, Trend vector, and the Edge risk-reward ratio. "
     "The Pattern Reasoning section explains exactly why the algorithm flagged this stock — "
     "showing the specific conditions that were met. "
     "And at the bottom — three critical trade levels: the Entry injection zone, the Target extraction price, "
     "and the Stop eject price. Plus a visual fit score bar showing the overall pattern confidence."),

    ("06_chart",
     "Here is the most powerful feature — the Interactive Pattern Chart. "
     "As soon as the scan completes, the top-ranked entity is automatically loaded into the chart. "
     "You get a full candlestick chart powered by TradingView's Lightweight Charts library, "
     "with a volume histogram overlaid at the bottom. "
     "The dashed yellow line is the Pattern Formation Highlight — it traces the exact shape of the detected pattern. "
     "For Cup and Handle, it draws the U-shaped rounded base and the handle pullback. "
     "The chart also shows price lines for your Entry, Target, and Stop levels in blue, green, and red."),

    ("07_interactive",
     "The chart is fully interactive. Click any stock card and the chart instantly updates to that entity. "
     "Here we click CDSL — and the Cup and Handle formation on C-D-S-L appears immediately. "
     "Now clicking Asian Paints — again, the formation adapts to this specific stock's price action. "
     "You can zoom, pan, and use the crosshair to inspect individual candles in detail. "
     "This gives you an instant visual confirmation of the pattern before making any trading decision."),

    ("08_second_strategy",
     "Let's switch to a different strategy. Selecting Double Bottom — S-02. "
     "Running the scan now returns 55 matches, with TCS, Wipro, and ICICI Bank at the top scoring 92 out of 100. "
     "Clicking on Wipro — the chart now draws a W-shaped Double Bottom formation, "
     "showing the two relative lows, the neckline resistance, and the projected breakout zone. "
     "Each strategy produces its own unique pattern visualization on the same chart interface."),

    ("09_outro",
     "That is the complete feature set of the SWING Neural Pattern Extraction Terminal. "
     "Five heuristic strategies. Four smart filters. Real-time NSE data. "
     "Automated pattern detection and visual chart annotation — all in one unified interface. "
     "This tool is built for decision support, giving you the data and pattern context you need "
     "to identify potential swing trading setups with speed and precision. "
     "Thank you for watching."),
]

print("\nGenerating narration audio segments...")
for filename, text in segments:
    out_path = os.path.join(OUT, f"{filename}.wav")
    print(f"  -> {filename}.wav")
    engine.save_to_file(text, out_path)

engine.runAndWait()
print("\nAll narration segments generated successfully!")
print(f"Output folder: {OUT}")
