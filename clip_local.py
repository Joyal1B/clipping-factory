#!/usr/bin/env python3
"""Usine à clips — clip_local.py <fichier.mp4> [--render] [--lang en] [--model small]

Variante FICHIER LOCAL de clip.py (ex: vidéos Google Drive), sans yt-dlp/URL.
  1. clip_local.py video.mp4               → transcription → affiche infos.
                                             COCO sélectionne → work/<id>.clips.json
  2. clip_local.py video.mp4 --render      → rendu vertical v2 → clips_v2/

clips.json attendu (lu par render_v2.py) :
  [{"start": float, "end": float, "title": "...", "hashtags": ["#..",..], "intro": "hook optionnel"}]
"""
import sys, os, subprocess, json, re

if len(sys.argv) < 2:
    sys.exit("usage: clip_local.py <fichier.mp4> [--render] [--lang en] [--model small]")

SRCFILE = sys.argv[1]
RENDER  = "--render" in sys.argv

def opt(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default

LANG  = opt("--lang", "en")     # Vlog Cannes Creator US = anglais
MODEL = opt("--model", "small")
SPLIT = "--split" in sys.argv   # réactive le layout split (réaction/tuto). Défaut : plein cadre vlog
HERE  = os.path.dirname(os.path.abspath(__file__))
PY    = os.path.join(HERE, ".venv", "bin", "python")

if not os.path.exists(SRCFILE):
    sys.exit(f"[clip] fichier introuvable: {SRCFILE}")

base = os.path.splitext(os.path.basename(SRCFILE))[0]
vid  = re.sub(r'[^a-zA-Z0-9_-]+', '_', base).strip('_')[:60] or "clip"

os.makedirs(f"{HERE}/work", exist_ok=True)
src = os.path.abspath(SRCFILE)
trj = f"{HERE}/work/{vid}.transcript.json"
clj = f"{HERE}/work/{vid}.clips.json"

def run(cmd, env=None):
    print(f"\n$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, env=env)

if not os.path.exists(trj):
    run([PY, f"{HERE}/transcribe.py", src, trj, MODEL, LANG])

if RENDER:
    if not os.path.exists(clj):
        sys.exit(f"[clip] {clj} manquant — sélectionne les moments d'abord (clips.json).")
    env = dict(os.environ)
    if not SPLIT:
        env["CLIP_TRACK"] = "1"               # vlog : suivi YOLO du sujet (Creator), focus gardé
        env.setdefault("CLIP_FULLFRAME", "1") # fallback plein cadre si track indispo
    run([PY, f"{HERE}/render_v2.py", trj, clj, src, f"{HERE}/clips_v2"], env=env)
    print("\n🎬 Clips prêts dans ./clips_v2/ (mp4 + .txt titre/hashtags)")
else:
    tr = json.load(open(trj, encoding="utf-8"))
    segs = tr.get("segments", [])
    dur = tr.get("duration") or (segs[-1]["end"] if segs else 0)
    print(f"\n✅ Transcript prêt : {trj}")
    print(f"   id={vid} · durée {dur/60:.1f} min · {len(segs)} segments · langue {tr.get('language')}")
    print(f"   → COCO sélectionne les moments forts → {clj}")
    print(f"   → puis : clip_local.py '{SRCFILE}' --render")
