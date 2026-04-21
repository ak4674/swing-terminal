"""
build_demo_video.py
Assembles the Swing Terminal Feature Demo Video by:
1. Converting the browser WebP recording to MP4
2. Concatenating all narration WAV files into one audio track
3. Merging audio + video into the final MP4
"""
import os
import subprocess
import glob

WEBP_SOURCE = r"C:\Users\akyan\.gemini\antigravity\brain\74eca8e6-ac3d-482d-a609-006d6c0e2b6f\swing_terminal_full_demo_1776517231405.webp"
ASSETS_DIR  = r"C:\Users\akyan\OneDrive\Desktop\Anand\Stock Screener\files\swing-terminal\demo_assets"
OUTPUT_DIR  = r"C:\Users\akyan\OneDrive\Desktop\Anand\Stock Screener\files\swing-terminal"
TEMP_DIR    = os.path.join(ASSETS_DIR, "tmp")
os.makedirs(TEMP_DIR, exist_ok=True)

RAW_VIDEO   = os.path.join(TEMP_DIR, "browser_raw.mp4")
FULL_AUDIO  = os.path.join(TEMP_DIR, "full_narration.wav")
FINAL_MP4   = os.path.join(OUTPUT_DIR, "SwingTerminal_Feature_Demo.mp4")

def run(cmd, label=""):
    print(f"\n▶ {label}")
    print(f"  CMD: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr[-800:] if result.stderr else 'none'}")
        print(f"  STDOUT: {result.stdout[-400:] if result.stdout else 'none'}")
        return False
    print(f"  OK")
    return True

# ── STEP 1: Convert WebP/WebM to raw MP4 ───────────────────────────────────
print("\n═══ STEP 1: Convert browser recording → MP4 ═══")
ok = run([
    "ffmpeg", "-y",
    "-i", WEBP_SOURCE,
    "-vf", "scale=1440:900:flags=lanczos,fps=30",
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "20",
    "-pix_fmt", "yuv420p",
    "-movflags", "+faststart",
    RAW_VIDEO
], "Converting source recording to H.264 MP4")

if not ok:
    # Try without scale filter — source may already be correct size
    run([
        "ffmpeg", "-y",
        "-i", WEBP_SOURCE,
        "-fps_mode", "vfr",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        RAW_VIDEO
    ], "Retry conversion without scale")

# ── STEP 2: Concatenate all narration WAVs ─────────────────────────────────
print("\n═══ STEP 2: Merge narration audio segments ═══")
wav_files = sorted(glob.glob(os.path.join(ASSETS_DIR, "*.wav")))
print(f"  Found {len(wav_files)} WAV files")

# Build ffmpeg concat list
concat_file = os.path.join(TEMP_DIR, "audio_concat.txt")
with open(concat_file, "w") as f:
    for wav in wav_files:
        f.write(f"file '{wav}'\n")

run([
    "ffmpeg", "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", concat_file,
    "-c:a", "pcm_s16le",
    FULL_AUDIO
], "Concatenating narration segments into single WAV")

# ── STEP 3: Get durations ──────────────────────────────────────────────────
def get_duration(path):
    try:
        result = subprocess.run([
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path
        ], capture_output=True, text=True)
        return float(result.stdout.strip())
    except:
        return 0.0

vid_dur = get_duration(RAW_VIDEO)
aud_dur = get_duration(FULL_AUDIO)
print(f"\n  Video duration: {vid_dur:.1f}s")
print(f"  Audio duration: {aud_dur:.1f}s")

# ── STEP 4: Combine video + audio, looping video if audio is longer ─────────
print("\n═══ STEP 3: Combine video + narration audio ═══")
if aud_dur > 0 and vid_dur > 0:
    # Determine final duration — use whichever is longer, but cap at audio
    target_dur = max(vid_dur, aud_dur)

    run([
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", RAW_VIDEO,    # loop video
        "-i", FULL_AUDIO,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-t", str(aud_dur),                        # cut to audio length
        "-movflags", "+faststart",
        FINAL_MP4
    ], "Merging video + audio into final MP4")
else:
    # Fallback — just re-encode video without audio
    print("  ⚠ Could not merge audio — saving video only")
    run([
        "ffmpeg", "-y",
        "-i", RAW_VIDEO,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        FINAL_MP4
    ], "Re-encoding video (no audio)")

# ── STEP 5: Report ─────────────────────────────────────────────────────────
if os.path.exists(FINAL_MP4):
    size_mb = os.path.getsize(FINAL_MP4) / (1024 * 1024)
    final_dur = get_duration(FINAL_MP4)
    print(f"\n✅ FINAL VIDEO READY")
    print(f"   Path: {FINAL_MP4}")
    print(f"   Size: {size_mb:.1f} MB")
    print(f"   Duration: {final_dur:.1f}s ({final_dur/60:.1f} min)")
else:
    print("\n❌ Final MP4 was not created — check errors above")
