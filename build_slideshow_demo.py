"""
build_slideshow_demo.py
Creates a polished feature demo video from screenshots + AI narration
"""
import os, subprocess, shutil, glob

FF = r"C:\Users\akyan\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe"
SCREENSHOTS_DIR = r"C:\Users\akyan\.gemini\antigravity\brain\74eca8e6-ac3d-482d-a609-006d6c0e2b6f\.system_generated\click_feedback"
ASSETS_DIR    = r"C:\Users\akyan\OneDrive\Desktop\Anand\Stock Screener\files\swing-terminal\demo_assets"
TEMP_DIR      = os.path.join(ASSETS_DIR, "tmp")
OUTPUT_DIR    = r"C:\Users\akyan\OneDrive\Desktop\Anand\Stock Screener\files\swing-terminal"
FINAL_MP4     = os.path.join(OUTPUT_DIR, "SwingTerminal_Feature_Demo.mp4")

os.makedirs(TEMP_DIR, exist_ok=True)

def run(cmd, label=""):
    print(f"\n>>> {label}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        print(f"    STDERR: {result.stderr[-600:]}")
    else:
        print(f"    OK")
    return result.returncode == 0

# ── Collect all PNGs from demo session (only the ones from the full demo) ──
all_pngs = sorted(glob.glob(os.path.join(SCREENSHOTS_DIR, "click_feedback_17765172*.png")))
print(f"Found {len(all_pngs)} demo screenshots")

# ── Copy & rename sequentially ──────────────────────────────────────────────
frames_dir = os.path.join(TEMP_DIR, "frames")
os.makedirs(frames_dir, exist_ok=True)

# Each frame holds for ~7 seconds so demo covers all screenshots at good pace
frame_duration = 7  # seconds per screenshot
fps = 25

for i, src in enumerate(all_pngs):
    for f in range(frame_duration * fps):
        dst = os.path.join(frames_dir, f"frame_{i:03d}_{f:04d}.png")
        if not os.path.exists(dst):
            shutil.copy2(src, dst)

print(f"Frames directory populated for {len(all_pngs)} slides x {frame_duration}s = {len(all_pngs)*frame_duration}s video")

# ── Concatenate all WAV narration files ─────────────────────────────────────
wav_files = sorted(glob.glob(os.path.join(ASSETS_DIR, "*.wav")))
print(f"\nFound {len(wav_files)} narration WAV files")
concat_list = os.path.join(TEMP_DIR, "aud_list.txt")
with open(concat_list, "w", encoding="utf-8") as f:
    for w in wav_files:
        f.write(f"file '{w}'\n")

full_audio = os.path.join(TEMP_DIR, "full_narration.wav")
run([FF, "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
     "-c:a", "pcm_s16le", full_audio], "Concatenate narration audio")

# Get audio duration
aud_probe = subprocess.run([
    FF.replace("ffmpeg.exe","ffprobe.exe"), "-v", "quiet",
    "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", full_audio
], capture_output=True, text=True)
aud_dur = float(aud_probe.stdout.strip()) if aud_probe.stdout.strip() else 0
print(f"Audio duration: {aud_dur:.1f}s = {aud_dur/60:.1f} min")

# ── Build slideshow video from frame PNGs ───────────────────────────────────
slideshow_mp4 = os.path.join(TEMP_DIR, "slideshow.mp4")
run([
    FF, "-y",
    "-framerate", str(fps),
    "-pattern_type", "glob",
    "-i", os.path.join(frames_dir, "frame_*.png"),
    "-vf", "scale=1280:960:flags=lanczos,pad=1280:720:0:0:black",  # pad to 16:9
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "20",
    "-pix_fmt", "yuv420p",
    "-movflags", "+faststart",
    slideshow_mp4
], "Build slideshow video from screenshots")

# Check slideshow duration
vid_probe = subprocess.run([
    FF.replace("ffmpeg.exe","ffprobe.exe"), "-v", "quiet",
    "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", slideshow_mp4
], capture_output=True, text=True)
vid_dur = float(vid_probe.stdout.strip()) if vid_probe.stdout.strip() else 0
print(f"Video duration: {vid_dur:.1f}s")

# ── Merge video + audio ──────────────────────────────────────────────────────
target_dur = aud_dur if aud_dur > 0 else vid_dur
print(f"Final video will be {target_dur:.1f}s")

run([
    FF, "-y",
    "-stream_loop", "-1", "-i", slideshow_mp4,   # loop slideshow if audio longer
    "-i", full_audio,
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "20",
    "-c:a", "aac",
    "-b:a", "192k",
    "-pix_fmt", "yuv420p",
    "-t", str(target_dur),
    "-movflags", "+faststart",
    FINAL_MP4
], "Merge slideshow + narration into final MP4")

# ── Report ───────────────────────────────────────────────────────────────────
if os.path.exists(FINAL_MP4):
    size = os.path.getsize(FINAL_MP4) / (1024*1024)
    final_probe = subprocess.run([
        FF.replace("ffmpeg.exe","ffprobe.exe"), "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", FINAL_MP4
    ], capture_output=True, text=True)
    fdur = float(final_probe.stdout.strip()) if final_probe.stdout.strip() else 0

    print(f"\n{'='*50}")
    print(f"  FINAL DEMO VIDEO READY")
    print(f"  File : {FINAL_MP4}")
    print(f"  Size : {size:.1f} MB")
    print(f"  Duration: {fdur:.1f}s ({fdur/60:.1f} min)")
    print(f"{'='*50}")
else:
    print("\nFINAL MP4 NOT CREATED - check errors above")
