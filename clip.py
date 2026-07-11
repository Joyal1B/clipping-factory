#!/usr/bin/env python3
"""Usine à clips — clip.py <url> [--render]

Flux en 2 temps (sélection des moments par COCO, pas par un LLM tiers) :
  1. clip.py <url>            → download + transcription, puis affiche le transcript.
                                COCO lit, choisit les meilleurs moments, écrit work/<id>.clips.json
  2. clip.py <url> --render   → rendu vertical v2 (moteur render_v2.py) → clips_v2/
"""
import sys, os, subprocess, json

if len(sys.argv) < 2:
    sys.exit("usage: clip.py <url> [--render]")
URL    = sys.argv[1]
RENDER = "--render" in sys.argv
HERE   = os.path.dirname(os.path.abspath(__file__))
PY     = os.path.join(HERE, ".venv", "bin", "python")

def run(cmd, **kw):
    print(f"\n$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, **kw)

try:
    vid = subprocess.check_output(
        ["yt-dlp", "--no-warnings", "--print", "%(id)s", URL]).decode().strip().splitlines()[0]
except subprocess.CalledProcessError:
    sys.exit("[clip] yt-dlp : impossible de lire l'URL")

os.makedirs(f"{HERE}/sources", exist_ok=True)
os.makedirs(f"{HERE}/work", exist_ok=True)
src = f"{HERE}/sources/{vid}.mp4"
trj = f"{HERE}/work/{vid}.transcript.json"
clj = f"{HERE}/work/{vid}.clips.json"

if not os.path.exists(src):
    # préférer H.264 (avc1) : décodable par cv2/PySceneDetect/tous les outils, pas d'AV1
    run(["yt-dlp", "-f",
         "bestvideo[height<=1080][vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/"
         "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
         "--merge-output-format", "mp4", "-o", f"{HERE}/sources/%(id)s.%(ext)s", URL])
if not os.path.exists(trj):
    run([PY, f"{HERE}/transcribe.py", src, trj, os.environ.get("WHISPER_MODEL", "small")])

if RENDER:
    if not os.path.exists(clj):
        sys.exit(f"[clip] {clj} manquant — sélectionne d'abord les moments (clips.json), puis relance avec --render.")
    run([PY, f"{HERE}/render_v2.py", trj, clj, src, f"{HERE}/clips_v2"])
    print("\n🎬 Clips prêts dans ./clips_v2/ (mp4 + .txt titre/hashtags)")
else:
    tr = json.load(open(trj, encoding="utf-8"))
    segs = tr.get("segments", [])
    dur = tr.get("duration") or (segs[-1]["end"] if segs else 0)
    print(f"\n✅ Transcript prêt : {trj}")
    print(f"   durée {dur/60:.1f} min · {len(segs)} segments")
    print(f"   → COCO sélectionne les moments forts → écrit {clj}")
    print(f"   → puis : clip.py {URL} --render")
