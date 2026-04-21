"""
build_demo_v2.py  -  Works on Windows ffmpeg (no glob)
Uses image concat list + narration to build final MP4 demo
"""
import os, subprocess, glob, shutil

FF   = r"C:\Users\akyan\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe"
FFP  = FF.replace("ffmpeg.exe", "ffprobe.exe")

SCREENSHOTS = r"C:\Users\akyan\.gemini\antigravity\brain\74eca8e6-ac3d-482d-a609-006d6c0e2b6f\.system_generated\click_feedback"
ASSETS      = r"C:\Users\akyan\OneDrive\Desktop\Anand\Stock Screener\files\swing-terminal\demo_assets"
TEMP        = os.path.join(ASSETS, "tmp")
OUTPUT      = r"C:\Users\akyan\OneDrive\Desktop\Anand\Stock Screener\files\swing-terminal\SwingTerminal_Feature_Demo.mp4"

os.makedirs(TEMP, exist_ok=True)

def run(cmd, label=""):
    print(f"\n[{label}]")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout + r.stderr)[-800:]
    if r.returncode != 0:
        print(f"  FAIL (code {r.returncode}):\n{out}")
    else:
        print(f"  OK")
    return r.returncode == 0

def probe_dur(path):
    r = subprocess.run([FFP, "-v","quiet","-show_entries","format=duration",
                        "-of","default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except: return 0.0

# ─── 1. COLLECT SCREENSHOTS ────────────────────────────────────────────────
pngs = sorted(glob.glob(os.path.join(SCREENSHOTS, "click_feedback_17765172*.png")))
print(f"Screenshots found: {len(pngs)}")
for p in pngs:
    print(f"  {os.path.basename(p)}")

# ─── 2. BUILD IMAGE CONCAT LIST ────────────────────────────────────────────
# Each image shown for a fixed duration
img_dur = 7  # seconds per slide
img_list_path = os.path.join(TEMP, "img_list.txt")
with open(img_list_path, "w", encoding="utf-8") as f:
    for png in pngs:
        f.write(f"file '{png.replace(chr(92), '/')}'\n")
        f.write(f"duration {img_dur}\n")
    # Repeat last frame to avoid ffmpeg dropping it
    if pngs:
        f.write(f"file '{pngs[-1].replace(chr(92), '/')}'\n")

print(f"Image list written: {len(pngs)} slides x {img_dur}s = ~{len(pngs)*img_dur}s")

# ─── 3. BUILD SILENT SLIDESHOW VIDEO ───────────────────────────────────────
slideshow = os.path.join(TEMP, "slideshow.mp4")
run([
    FF, "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", img_list_path,
    "-vf", "scale=1280:800:force_original_aspect_ratio=decrease,pad=1280:800:(ow-iw)/2:(oh-ih)/2:black",
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "20",
    "-pix_fmt", "yuv420p",
    "-r", "25",
    "-movflags", "+faststart",
    slideshow
], "Build slideshow from screenshots")

vid_dur = probe_dur(slideshow)
print(f"Slideshow video duration: {vid_dur:.1f}s")

# ─── 4. CONCAT NARRATION AUDIO ─────────────────────────────────────────────
wavs = sorted(glob.glob(os.path.join(ASSETS, "*.wav")))
print(f"Narration WAV files: {len(wavs)}")

aud_list = os.path.join(TEMP, "aud_list.txt")
with open(aud_list, "w", encoding="utf-8") as f:
    for w in wavs:
        f.write(f"file '{w.replace(chr(92), '/')}'\n")

full_audio = os.path.join(TEMP, "narration.wav")
run([
    FF, "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", aud_list,
    "-c:a", "pcm_s16le",
    full_audio
], "Concatenate narration segments")

aud_dur = probe_dur(full_audio)
print(f"Total narration: {aud_dur:.1f}s = {aud_dur/60:.1f} min")

# ─── 5. MERGE VIDEO + AUDIO (loop video to match audio) ──────────────────
target = aud_dur if aud_dur > 0 else vid_dur
print(f"Target duration: {target:.1f}s")

ok = run([
    FF, "-y",
    "-stream_loop", "-1",       # loop slideshow
    "-i", slideshow,
    "-i", full_audio,
    "-map", "0:v:0",
    "-map", "1:a:0",
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "20",
    "-c:a", "aac",
    "-b:a", "192k",
    "-t", str(target),
    "-pix_fmt", "yuv420p",
    "-movflags", "+faststart",
    OUTPUT
], "Merge slideshow + narration → Final MP4")

# ─── 6. REPORT ─────────────────────────────────────────────────────────────
if os.path.exists(OUTPUT):
    size = os.path.getsize(OUTPUT) / (1024*1024)
    dur  = probe_dur(OUTPUT)
    print(f"\n{'='*55}")
    print(f"  FINAL DEMO VIDEO READY")
    print(f"  File     : {OUTPUT}")
    print(f"  Size     : {size:.1f} MB")
    print(f"  Duration : {dur:.1f}s  ({dur/60:.1f} min)")
    print(f"{'='*55}")
else:
    print("\n[ERROR] Final MP4 was not produced.")
