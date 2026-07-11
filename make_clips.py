#!/usr/bin/env python3
"""Découpe + reframe 9:16 + sous-titres animés brûlés, à partir d'un transcript et d'une liste de clips."""
import sys, json, os, subprocess, re

TRANSCRIPT = sys.argv[1]          # work/<id>.transcript.json
CLIPS_JSON = sys.argv[2]          # work/<id>.clips.json
SOURCE     = sys.argv[3]          # sources/<id>.mp4
OUTDIR     = sys.argv[4]          # clips/
FONT       = os.environ.get("CLIP_FONT", "DejaVu Sans")

os.makedirs(OUTDIR, exist_ok=True)
tr = json.load(open(TRANSCRIPT, encoding="utf-8"))
clips = json.load(open(CLIPS_JSON, encoding="utf-8"))

def clean_word(w):
    w = w.strip()
    w = re.sub(r'^\d+[,\.]+(?=[A-Za-zÀ-ÿ])', '', w)   # "0,,un" -> "un" (glitch Whisper)
    w = re.sub(r'[,]{2,}', ',', w)                      # virgules multiples
    return w.strip()

# tous les mots à plat (nettoyés)
ALL_WORDS = []
for seg in tr["segments"]:
    for w in (seg.get("words") or []):
        cw = clean_word(w["word"])
        if cw:
            ALL_WORDS.append({"start": w["start"], "end": w["end"], "word": cw})

def ass_time(t):
    if t < 0: t = 0
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:01d}:{m:02d}:{s:05.2f}"

def words_in(a, b):
    return [w for w in ALL_WORDS if w["end"] > a and w["start"] < b]

def chunk_words(words, max_words=3, max_chars=14, max_gap=0.7):
    """Regroupe les mots en petits blocs façon sous-titres TikTok."""
    chunks, cur = [], []
    for w in words:
        if cur:
            gap = w["start"] - cur[-1]["end"]
            chars = sum(len(x["word"]) + 1 for x in cur) + len(w["word"])
            if len(cur) >= max_words or chars > max_chars or gap > max_gap:
                chunks.append(cur); cur = []
        cur.append(w)
    if cur: chunks.append(cur)
    return chunks

ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,{FONT},80,&H00FFFFFF,&H0000F0FF,&H00000000,&H64000000,-1,0,0,0,100,100,1,0,1,6,3,2,90,90,500,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text
"""

def build_ass(clip_start, clip_end, path):
    ws = words_in(clip_start, clip_end)
    lines = [ASS_HEADER]
    for ch in chunk_words(ws):
        st = max(0, ch[0]["start"] - clip_start)
        en = ch[-1]["end"] - clip_start
        txt = " ".join(x["word"] for x in ch).upper().replace("\n", " ")
        # léger pop-in
        eff = "{\\fad(80,40)\\t(0,120,\\fscx112\\fscy112)\\t(120,200,\\fscx100\\fscy100)}"
        lines.append(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},Pop,,0,0,,{eff}{txt}")
    open(path, "w", encoding="utf-8").write("\n".join(lines))

def render(idx, clip):
    start, end = float(clip["start"]), float(clip["end"])
    dur = end - start
    base = f"clip_{idx:02d}"
    ass = os.path.join(OUTDIR, base + ".ass")
    out = os.path.join(OUTDIR, base + ".mp4")
    build_ass(start, end, ass)
    # crop centré 9:16 depuis 16:9 → scale 1080x1920 → burn sous-titres
    vf = (f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,"
          f"subtitles='{ass}':fontsdir=/usr/share/fonts")
    cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", SOURCE, "-t", str(dur),
           "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out]
    print(f"[render] {base}  {start:.1f}→{end:.1f} ({dur:.0f}s)  « {clip.get('title','')[:50]} »", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-800:]); return
    # fichier texte prêt-à-poster
    tags = " ".join(clip.get("hashtags", []))
    open(os.path.join(OUTDIR, base + ".txt"), "w", encoding="utf-8").write(
        f"{clip.get('title','')}\n\n{tags}\n")
    print(f"        ✅ {out}", flush=True)

for i, c in enumerate(clips, 1):
    render(i, c)
print(f"\n[make_clips] {len(clips)} clips générés dans {OUTDIR}")
