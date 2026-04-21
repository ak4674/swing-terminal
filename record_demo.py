# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
record_demo.py
==============
Records browser navigation timed exactly to each narration audio segment,
then stitches the recordings with the WAV audio into a final MP4.

Segment timing (from WAV durations):
  00_intro        20.7s  — landing page, status hub
  01_header       19.1s  — zoom header, status bar animation
  02_strategies   54.8s  — cycle through all 5 strategy cards
  03_filters      46.1s  — demonstrate all 4 filters
  04_scan         27.9s  — click Execute Scan, wait for results
  05_cards        53.3s  — scroll through result cards, highlight metrics
  06_chart        37.6s  — chart loads, show pattern line + price lines
  07_interactive  31.2s  — click CDSL → Asian Paints, crosshair demo
  08_second_strat 32.1s  — switch to Double Bottom, scan, click Wipro chart
  09_outro        29.1s  — slow scroll up, static hero shot
"""

import os, subprocess, time, threading
from playwright.sync_api import sync_playwright

# ─── PATHS ────────────────────────────────────────────────────────────────────
FF     = r"C:\Users\akyan\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe"
FFP    = FF.replace("ffmpeg.exe", "ffprobe.exe")
ASSETS = r"C:\Users\akyan\OneDrive\Desktop\Anand\Stock Screener\files\swing-terminal\demo_assets"
TEMP   = os.path.join(ASSETS, "tmp_rec")
OUTPUT = r"C:\Users\akyan\OneDrive\Desktop\Anand\Stock Screener\files\swing-terminal\SwingTerminal_Feature_Demo.mp4"
URL    = "http://localhost:8000"

os.makedirs(TEMP, exist_ok=True)

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def run_ff(cmd, label=""):
    print(f"\n[ffmpeg] {label}")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout + r.stderr)[-1200:]
    if r.returncode != 0:
        print(f"  FAIL:\n{out}")
    else:
        print(f"  OK")
    return r.returncode == 0

def probe_dur(path):
    r = subprocess.run([FFP, "-v","quiet","-show_entries","format=duration",
                        "-of","default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except: return 0.0

def wait(sec, label=""):
    """Sleep in small increments with progress dots."""
    print(f"  [wait {sec}s] {label}", end="", flush=True)
    for _ in range(int(sec)):
        time.sleep(1)
        print(".", end="", flush=True)
    rem = sec - int(sec)
    if rem > 0:
        time.sleep(rem)
    print()

# ─── SEGMENT DURATIONS (measured from WAVs) ───────────────────────────────────
SEGS = [
    ("00_intro",         20.7),
    ("01_header",        19.1),
    ("02_strategies",    54.8),
    ("03_filters",       46.1),
    ("04_scan",          27.9),
    ("05_cards",         53.3),
    ("06_chart",         37.6),
    ("07_interactive",   31.2),
    ("08_second_strat",  32.1),
    ("09_outro",         29.1),
]

# ─── MAIN RECORDING ───────────────────────────────────────────────────────────
def record_screen():
    """
    Uses Playwright video recording (WebM) for each segment separately.
    Each segment is saved as TEMP/<seg_name>.webm
    """
    seg_files = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--start-maximized",
                "--disable-infobars",
            ]
        )

        # ── Create ONE context/page — we'll record segments by
        #    starting/stopping video capture between sections.
        #    Playwright records video per-context so we create a fresh
        #    context for each segment.

        # ── PRE-LOAD: wait for backend cache ──────────────────────────────
        print("\n[Pre-check] Waiting for backend to have stocks cached...")
        ctx0 = browser.new_context(viewport={"width": 1280, "height": 800})
        pg0  = ctx0.new_page()
        pg0.goto(URL + "/api/status", wait_until="domcontentloaded")
        for _ in range(60):
            try:
                data = pg0.evaluate("() => JSON.parse(document.body.innerText)")
                if data.get("ready"):
                    print(f"  [OK] Cache ready: {data['stocks_cached']} stocks")
                    break
            except Exception:
                pass
            time.sleep(3)
            pg0.reload()
        ctx0.close()

        # ─────────────────────────────────────────────────────────────────
        # SEGMENT RECORDINGS
        # Each gets its own context so Playwright captures a separate video
        # ─────────────────────────────────────────────────────────────────

        for seg_name, duration in SEGS:
            print(f"\n{'=' * 60}")
            print(f">>  Recording  [{seg_name}]  ({duration}s)")

            seg_dir  = os.path.join(TEMP, seg_name)
            os.makedirs(seg_dir, exist_ok=True)

            ctx = browser.new_context(
                viewport={"width": 1280, "height": 800},
                record_video_dir=seg_dir,
                record_video_size={"width": 1280, "height": 800},
            )
            pg = ctx.new_page()

            try:
                # ── Navigate / interactions per segment ──────────────────

                if seg_name == "00_intro":
                    pg.goto(URL, wait_until="domcontentloaded")
                    pg.wait_for_timeout(1000)
                    # Smooth scroll to reveal full page
                    pg.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
                    wait(duration - 3)
                    pg.evaluate("window.scrollTo({top: 200, behavior: 'smooth'})")
                    wait(2)

                elif seg_name == "01_header":
                    pg.goto(URL, wait_until="domcontentloaded")
                    pg.wait_for_timeout(800)
                    # Hover over status items to show interactivity
                    pg.hover(".status-hub")
                    wait(4)
                    pg.hover(".logo")
                    wait(3)
                    pg.hover(".status-hub")
                    wait(duration - 9)

                elif seg_name == "02_strategies":
                    pg.goto(URL, wait_until="domcontentloaded")
                    pg.wait_for_timeout(1000)
                    # Wait for strategy cards to load
                    pg.wait_for_selector(".strat-card", timeout=10000)
                    wait(2)
                    cards = pg.query_selector_all(".strat-card")
                    # Hover each card with dwell
                    per_card = (duration - 5) / max(len(cards), 1)
                    for card in cards:
                        card.hover()
                        wait(per_card * 0.6)
                    # Click Cup & Handle (first) to select it
                    wait(2)
                    if cards:
                        cards[0].click()
                        wait(4)
                    # Briefly hover others
                    for card in cards[1:]:
                        card.hover()
                        wait(1.5)

                elif seg_name == "03_filters":
                    pg.goto(URL, wait_until="domcontentloaded")
                    pg.wait_for_timeout(800)
                    # Select Cup & Handle first
                    pg.wait_for_selector(".strat-card", timeout=10000)
                    pg.query_selector_all(".strat-card")[0].click()
                    wait(2)
                    # Market Universe
                    pg.select_option("#fCap", "large")
                    wait(4)
                    pg.hover("#fCap")
                    wait(2)
                    pg.select_option("#fCap", "mid")
                    wait(4)
                    pg.select_option("#fCap", "any")
                    wait(2)
                    # Sector
                    pg.select_option("#fSector", "Information Technology")
                    wait(4)
                    pg.select_option("#fSector", "Banking & Financials")
                    wait(4)
                    pg.select_option("#fSector", "any")
                    wait(2)
                    # Intelligence Grade
                    pg.select_option("#fScore", "60")
                    wait(3)
                    pg.select_option("#fScore", "80")
                    wait(3)
                    pg.select_option("#fScore", "0")
                    wait(2)
                    # Trend
                    pg.select_option("#fTrend", "bullish")
                    wait(4)
                    pg.select_option("#fTrend", "any")
                    wait(duration - 36)

                elif seg_name == "04_scan":
                    pg.goto(URL, wait_until="domcontentloaded")
                    pg.wait_for_timeout(800)
                    pg.wait_for_selector(".strat-card", timeout=10000)
                    # Select Cup & Handle
                    pg.query_selector_all(".strat-card")[0].click()
                    wait(2)
                    # Click Scan
                    pg.click("#runBtn")
                    wait(3)
                    # Wait for results
                    pg.wait_for_selector(".card", timeout=30000)
                    wait(duration - 6)

                elif seg_name == "05_cards":
                    pg.goto(URL, wait_until="domcontentloaded")
                    pg.wait_for_timeout(800)
                    pg.wait_for_selector(".strat-card", timeout=10000)
                    pg.query_selector_all(".strat-card")[0].click()
                    wait(1)
                    pg.click("#runBtn")
                    pg.wait_for_selector(".card", timeout=30000)
                    wait(2)
                    # Scroll down to see cards
                    pg.evaluate("window.scrollTo({top: 600, behavior: 'smooth'})")
                    wait(3)
                    cards = pg.query_selector_all(".card")
                    # Hover first 4 cards to show details
                    for i, card in enumerate(cards[:4]):
                        card.hover()
                        wait(6)
                        pg.evaluate(f"window.scrollBy({{top: 180, behavior: 'smooth'}})")
                        wait(2)

                elif seg_name == "06_chart":
                    pg.goto(URL, wait_until="domcontentloaded")
                    pg.wait_for_timeout(800)
                    pg.wait_for_selector(".strat-card", timeout=10000)
                    pg.query_selector_all(".strat-card")[0].click()
                    wait(1)
                    pg.click("#runBtn")
                    pg.wait_for_selector(".card", timeout=30000)
                    wait(2)
                    # Click first result card to trigger chart
                    pg.evaluate("window.scrollTo({top: 600, behavior: 'smooth'})")
                    wait(1)
                    cards = pg.query_selector_all(".card")
                    if cards:
                        cards[0].click()
                    # Scroll up to see chart
                    pg.evaluate("window.scrollTo({top: 350, behavior: 'smooth'})")
                    wait(4)
                    pg.wait_for_selector("#chart-container canvas", timeout=15000)
                    wait(duration - 10)

                elif seg_name == "07_interactive":
                    pg.goto(URL, wait_until="domcontentloaded")
                    pg.wait_for_timeout(800)
                    pg.wait_for_selector(".strat-card", timeout=10000)
                    pg.query_selector_all(".strat-card")[0].click()
                    wait(1)
                    pg.click("#runBtn")
                    pg.wait_for_selector(".card", timeout=30000)
                    wait(2)
                    pg.evaluate("window.scrollTo({top: 600, behavior: 'smooth'})")
                    wait(1)
                    cards = pg.query_selector_all(".card")
                    # Click first card (auto-loaded)
                    if len(cards) >= 1:
                        cards[0].click()
                    pg.evaluate("window.scrollTo({top: 300, behavior: 'smooth'})")
                    wait(5)
                    # Find CDSL card and click
                    cdsl = pg.query_selector("[data-symbol='CDSL']")
                    if cdsl:
                        pg.evaluate("window.scrollTo({top: 600, behavior: 'smooth'})")
                        wait(1)
                        cdsl.click()
                        pg.evaluate("window.scrollTo({top: 300, behavior: 'smooth'})")
                        wait(6)
                    # Find Asian Paints and click
                    ap = pg.query_selector("[data-symbol='ASIANPAINT']")
                    if ap:
                        pg.evaluate("window.scrollTo({top: 600, behavior: 'smooth'})")
                        wait(1)
                        ap.click()
                        pg.evaluate("window.scrollTo({top: 300, behavior: 'smooth'})")
                        wait(6)
                    wait(duration - 24)

                elif seg_name == "08_second_strat":
                    pg.goto(URL, wait_until="domcontentloaded")
                    pg.wait_for_timeout(800)
                    pg.wait_for_selector(".strat-card", timeout=10000)
                    # Click Double Bottom (second card)
                    cards_strat = pg.query_selector_all(".strat-card")
                    if len(cards_strat) >= 2:
                        cards_strat[1].click()
                    wait(2)
                    pg.click("#runBtn")
                    pg.wait_for_selector(".card", timeout=30000)
                    wait(3)
                    # Scroll to results
                    pg.evaluate("window.scrollTo({top: 600, behavior: 'smooth'})")
                    wait(2)
                    result_cards = pg.query_selector_all(".card")
                    # Click Wipro if found, else first card
                    wipro = pg.query_selector("[data-symbol='WIPRO']")
                    if wipro:
                        wipro.click()
                    elif result_cards:
                        result_cards[0].click()
                    # Scroll to chart
                    pg.evaluate("window.scrollTo({top: 300, behavior: 'smooth'})")
                    wait(duration - 10)

                elif seg_name == "09_outro":
                    pg.goto(URL, wait_until="domcontentloaded")
                    pg.wait_for_timeout(800)
                    pg.wait_for_selector(".strat-card", timeout=10000)
                    # Select Cup & Handle for a clean final shot
                    pg.query_selector_all(".strat-card")[0].click()
                    wait(2)
                    pg.click("#runBtn")
                    pg.wait_for_selector(".card", timeout=30000)
                    wait(2)
                    # Slow scroll to top for hero shot
                    pg.evaluate("window.scrollTo({top: 400, behavior: 'smooth'})")
                    wait(4)
                    pg.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
                    wait(duration - 10)

            except Exception as e:
                print(f"  [ERR] Error in {seg_name}: {e}")
                wait(2)

            # Close context → Playwright finalizes the video
            pg.close()
            ctx.close()

            # Find the generated webm
            webms = [f for f in os.listdir(seg_dir) if f.endswith(".webm")]
            if webms:
                src = os.path.join(seg_dir, webms[0])
                dst = os.path.join(TEMP, f"{seg_name}.webm")
                os.replace(src, dst)
                seg_files.append((seg_name, duration, dst))
                print(f"  [OK] Saved: {dst}")
            else:
                print(f"  [MISS] No webm found for {seg_name}")

        browser.close()

    return seg_files


# ─── CONVERT WEBM → MP4 CLIPS ─────────────────────────────────────────────────
def convert_clips(seg_files):
    mp4_clips = []
    for seg_name, duration, webm_path in seg_files:
        mp4_path = os.path.join(TEMP, f"{seg_name}.mp4")
        ok = run_ff([
            FF, "-y",
            "-i", webm_path,
            # Re-encode + trim to exact audio duration
            "-t", str(duration),
            "-vf", "scale=1280:800:force_original_aspect_ratio=decrease,pad=1280:800:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-an",
            mp4_path
        ], f"Convert {seg_name}.webm → mp4 ({duration}s)")
        if ok:
            mp4_clips.append((seg_name, mp4_path))
    return mp4_clips


# ─── CONCAT ALL CLIPS ─────────────────────────────────────────────────────────
def concat_video(mp4_clips):
    concat_txt = os.path.join(TEMP, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for _, mp4 in mp4_clips:
            f.write(f"file '{mp4.replace(chr(92), '/')}'\n")
    
    silent_video = os.path.join(TEMP, "silent_video.mp4")
    run_ff([
        FF, "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_txt,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        silent_video
    ], "Concatenate video clips → silent_video.mp4")
    return silent_video


# ─── CONCAT AUDIO ─────────────────────────────────────────────────────────────
def concat_audio():
    wavs = sorted([
        os.path.join(ASSETS, f)
        for f in os.listdir(ASSETS)
        if f.endswith(".wav")
    ])
    aud_txt = os.path.join(TEMP, "aud_list.txt")
    with open(aud_txt, "w", encoding="utf-8") as f:
        for w in wavs:
            f.write(f"file '{w.replace(chr(92), '/')}'\n")
    full_audio = os.path.join(TEMP, "narration.wav")
    run_ff([
        FF, "-y",
        "-f", "concat", "-safe", "0",
        "-i", aud_txt,
        "-c:a", "pcm_s16le",
        full_audio
    ], "Concat narration WAVs")
    return full_audio


# ─── MERGE VIDEO + AUDIO ──────────────────────────────────────────────────────
def merge(silent_video, full_audio):
    aud_dur = probe_dur(full_audio)
    vid_dur = probe_dur(silent_video)
    target  = aud_dur if aud_dur > 0 else vid_dur
    print(f"\nVideo: {vid_dur:.1f}s  |  Audio: {aud_dur:.1f}s  |  Target: {target:.1f}s")

    # If video is shorter than audio, loop it
    if vid_dur < aud_dur - 1:
        v_input = ["-stream_loop", "-1", "-i", silent_video]
    else:
        v_input = ["-i", silent_video]

    run_ff([
        FF, "-y",
        *v_input,
        "-i", full_audio,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(target),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        OUTPUT
    ], "Merge video + narration → Final MP4")


# ─── RUN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 65)
    print("  SWING Terminal — Timed Screen Recording")
    print("=" * 65)

    # 1. Record
    seg_files = record_screen()
    print(f"\nRecorded {len(seg_files)}/{len(SEGS)} segments.")

    # 2. Convert webm → mp4 clips
    mp4_clips = convert_clips(seg_files)

    # 3. Concat video
    silent_video = concat_video(mp4_clips)

    # 4. Concat audio
    full_audio = concat_audio()

    # 5. Merge
    merge(silent_video, full_audio)

    # 6. Report
    if os.path.exists(OUTPUT):
        size = os.path.getsize(OUTPUT) / (1024 * 1024)
        dur  = probe_dur(OUTPUT)
        print(f"\n{'='*65}")
        print("  [DONE] FINAL DEMO VIDEO READY")
        print(f"  File     : {OUTPUT}")
        print(f"  Size     : {size:.1f} MB")
        print(f"  Duration : {dur:.1f}s  ({dur/60:.1f} min)")
        print(f"{'='*65}")
    else:
        print("\n[ERROR] Final MP4 not produced.")
