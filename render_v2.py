#!/usr/bin/env python3
"""Moteur de rendu v2.1 — layout adaptatif (face-track plein cadre / split 50-50) + sous-titres karaoké.
Robuste : résolution source auto-sondée, bande de sous-titres incrustés auto-détectée,
sources non-16:9 gérées, chaque clip isolé (un échec ne tue pas le batch).
usage: render_v2.py <transcript.json> <clips.json> <source.mp4> <outdir> [--only N]
env  : CLIP_SUBCUT=auto|0|<px>   CLIP_FONT="DejaVu Sans"
"""
import sys, json, os, subprocess, re, glob, shutil
import cv2

TRANSCRIPT, CLIPS_JSON, SOURCE, OUTDIR = sys.argv[1:5]
ONLY = None
if "--only" in sys.argv:
    ONLY = int(sys.argv[sys.argv.index("--only") + 1])
FONT = os.environ.get("CLIP_FONT", "DejaVu Sans")
# Vlog/lifestyle : force le plein cadre 9:16 face-track sur TOUTES les scènes,
# jamais de split 50-50 (présentateur bouclé en haut). Activer avec CLIP_FULLFRAME=1
FULLFRAME = os.environ.get("CLIP_FULLFRAME", "0").strip().lower() not in ("", "0", "false", "no", "off")
# Reframe dynamique YOLO : suit le sujet (silhouette) en continu, focus gardé même de dos/foule.
TRACK = os.environ.get("CLIP_TRACK", "0").strip().lower() not in ("", "0", "false", "no", "off")
TRACK_ZOOM = os.environ.get("CLIP_TRACK_ZOOM", "0").strip().lower() not in ("", "0", "false", "no", "off")
# TRACK_CENTER : reframe centré fixe (pas de suivi) — montages multi-plans / sous-titres source centrés.
TRACK_CENTER = os.environ.get("CLIP_TRACK_CENTER", "0").strip().lower() not in ("", "0", "false", "no", "off")
# FIT : letterbox 16:9 entier + fond flou (rien coupé) — vidéos très sous-titrées source (tour, teaser).
FIT = os.environ.get("CLIP_FIT", "0").strip().lower() not in ("", "0", "false", "no", "off")
# NOSUBS : ne brûle PAS les sous-titres karaoké (garde le hook d'intro). Pour les vidéos
# qui ont DÉJÀ des sous-titres source incrustés (tour de villa, teaser) → évite le doublon en bas.
NOSUBS = os.environ.get("CLIP_NOSUBS", "0").strip().lower() not in ("", "0", "false", "no", "off")
RF_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reframe_track.py")
W, H = 1080, 1920          # cadre vertical final
HALF = H // 2              # 960, hauteur d'une moitié pour le split

os.makedirs(OUTDIR, exist_ok=True)
WORK = os.path.join(OUTDIR, "_work"); os.makedirs(WORK, exist_ok=True)

if not os.path.exists(SOURCE):
    sys.exit(f"[v2] source introuvable: {SOURCE}")

# ---------- sonde résolution source (fini le 1920x1080 en dur) ----------
def ffprobe_dims(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path]).decode().strip()
    p = out.replace("\n", " ").split()[0].split("x")
    return int(p[0]), int(p[1])

SRC_W, SRC_H = ffprobe_dims(SOURCE)
LANDSCAPE = SRC_W >= SRC_H * 1.2     # sinon source portrait/carré → mode "fit"

# ---------- détection auto de la bande de sous-titres incrustés ----------
def detect_sub_band():
    """Renvoie la hauteur (px source) à couper en bas pour virer les sous-titres
    incrustés d'origine. 0 si rien de fiable. Override: CLIP_SUBCUT=auto|0|<px>.
    Méthode : vote de présence. Les sous-titres sont intermittents → on cherche une
    bande basse 'allumée' (forte densité de bords) dans une fraction significative des frames."""
    env = os.environ.get("CLIP_SUBCUT")
    if env is not None and env.strip().lower() != "auto":
        try:
            return max(0, int(env))
        except ValueError:
            pass
    if not LANDSCAPE:
        return 0
    try:
        import numpy as np
    except ImportError:
        return 0
    scan = os.path.join(WORK, "subscan"); shutil.rmtree(scan, ignore_errors=True); os.makedirs(scan)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", SOURCE,
                    "-vf", "thumbnail=n=200,scale=640:-2", "-frames:v", "24",
                    os.path.join(scan, "s_%03d.jpg")], check=False)
    frames = sorted(glob.glob(os.path.join(scan, "s_*.jpg")))
    if len(frames) < 6:
        return 0
    votes = None; sh = 0; nf = 0
    for fp in frames:
        img = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        sh = img.shape[0]
        rs = cv2.Canny(img, 90, 200).sum(axis=1).astype("float64")   # densité de bords par ligne
        m = rs.max()
        if m < 1:
            continue
        lit = (rs / m) > 0.45                       # lignes "allumées" de cette frame
        votes = lit.astype("float64") if votes is None else votes + lit
        nf += 1
    if nf < 6 or sh == 0:
        return 0
    frac = votes / nf                                # fraction de frames où la ligne est allumée
    bottom = int(sh * 0.84)                          # vrais sous-titres = tout en bas (16 %), pas le micro à mi-hauteur
    band = [i for i in range(bottom, sh) if frac[i] >= 0.30]
    if len(band) < 3:                                # bande trop fine → bruit (logo, UI b-roll), pas des sous-titres
        return 0
    cut_row = min(band) - int(sh * 0.01)            # petite marge au-dessus du texte
    cut_640 = sh - cut_row
    if not (sh * 0.04 <= cut_640 <= sh * 0.22):     # hauteur hors plage plausible d'une bande de sous-titres
        return 0
    return int(cut_640 * SRC_H / sh)

SUB_CUT  = detect_sub_band()
USABLE_H = SRC_H - SUB_CUT          # zone source sans les sous-titres d'origine
print(f"[v2] source {SRC_W}x{SRC_H} ({'paysage' if LANDSCAPE else 'portrait/carré'}) · sub_cut={SUB_CUT}px", flush=True)

tr = json.load(open(TRANSCRIPT, encoding="utf-8"))
clips = json.load(open(CLIPS_JSON, encoding="utf-8"))

# ---------- mots (pour sous-titres) ----------
# corrections de transcription (Whisper FR rate souvent les marques tech)
CORRECTIONS = [(r'(?i)chad\s*gpt', 'ChatGPT'), (r'(?i)open\s*eye', 'OpenAI'),
               (r'(?i)open\s*ia', 'OpenAI'), (r'(?i)mid\s*journey', 'Midjourney')]

def clean_word(w):
    w = w.strip()
    w = re.sub(r'^\d+[,\.]+(?=[A-Za-zÀ-ÿ])', '', w)
    w = re.sub(r'[,]{2,}', ',', w)
    for pat, rep in CORRECTIONS:
        w = re.sub(pat, rep, w)
    return w.strip()

ALL_WORDS = []
for seg in tr["segments"]:
    for w in (seg.get("words") or []):
        cw = clean_word(w["word"])
        if cw:
            ALL_WORDS.append({"start": w["start"], "end": w["end"], "word": cw})

def words_in(a, b):
    return [w for w in ALL_WORDS if w["end"] > a and w["start"] < b]

# ---------- détection visage (timeline) — MediaPipe BlazeFace (fallback Haar) ----------
SCAN_W = 640
CONF_MIN = 0.60   # seuil de confiance : écarte les fausses détections (grande box, faible score)
_FACE_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "blaze_face_short_range.tflite")
_MP = {"det": None, "mp": None, "ok": None}   # ok=None pas tenté · True dispo · False fallback
_HAAR = None

def _faces_mp(img_bgr):
    """Renvoie [(cx_norm, area_norm)] via MediaPipe BlazeFace, ou None si MP indisponible."""
    if _MP["ok"] is False:
        return None
    if _MP["det"] is None:
        try:
            os.environ.setdefault("GLOG_minloglevel", "3")
            import mediapipe as mp
            from mediapipe.tasks import python as mpp
            from mediapipe.tasks.python import vision as mpv
            _MP["mp"] = mp
            _MP["det"] = mpv.FaceDetector.create_from_options(
                mpv.FaceDetectorOptions(
                    base_options=mpp.BaseOptions(model_asset_path=_FACE_MODEL),
                    min_detection_confidence=0.5))
            _MP["ok"] = True
        except Exception as e:
            print(f"[v2] MediaPipe indispo ({e}) → fallback Haar", flush=True)
            _MP["ok"] = False
            return None
    mp = _MP["mp"]
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    res = _MP["det"].detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    h, w = img_bgr.shape[:2]
    return [((d.bounding_box.origin_x + d.bounding_box.width/2) / w,
             d.bounding_box.width * d.bounding_box.height / (w*h),
             d.categories[0].score) for d in res.detections]

def _faces_haar(img_bgr):
    global _HAAR
    if _HAAR is None:
        _HAAR = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = img_bgr.shape[:2]
    faces = _HAAR.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(64, 64))
    return [((x + fw/2) / w, fw*fh / (w*h), 0.99) for (x, y, fw, fh) in faces]

def face_timeline(start, dur, fps=3):
    """Échantillonne le clip à `fps` i/s, renvoie [(t_rel, has_face, cx_norm)].
    Détection MediaPipe BlazeFace (robuste profils, ~0 faux positif sur captures), fallback Haar."""
    scan = os.path.join(WORK, "scan"); shutil.rmtree(scan, ignore_errors=True); os.makedirs(scan)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-t", str(dur),
                    "-i", SOURCE, "-vf", f"fps={fps},scale={SCAN_W}:-1", os.path.join(scan, "f_%04d.jpg")],
                   check=True)
    frames = sorted(glob.glob(os.path.join(scan, "f_*.jpg")))
    out = []
    for i, fp in enumerate(frames):
        img = cv2.imread(fp)
        if img is None:
            out.append((i / fps, False, 0.5)); continue
        faces = _faces_mp(img)
        if faces is None:
            faces = _faces_haar(img)
        faces = [f for f in faces if f[2] >= CONF_MIN]    # écarte les fausses détections peu fiables
        if faces:
            cx, _, _ = max(faces, key=lambda f: f[1])     # plus grand visage fiable = le présentateur (proche)
            out.append((i / fps, True, min(max(cx, 0.0), 1.0)))
        else:
            out.append((i / fps, False, 0.5))
    return out

def shot_cuts(start, dur):
    """Coupures de plan réelles (PySceneDetect AdaptiveDetector). AV1-proof : on transcode
    d'abord la zone en H.264 480p via le ffmpeg statique (qui décode l'AV1) → cv2 lit ça.
    Renvoie les instants de coupure (relatifs au clip), [] si indisponible."""
    tmp = os.path.join(WORK, "scd.mp4")
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-t", str(dur),
                        "-i", SOURCE, "-an", "-vf", "scale=480:-2",
                        "-c:v", "libx264", "-preset", "ultrafast", tmp], check=True)
        from scenedetect import detect, AdaptiveDetector
        scenes = detect(tmp, AdaptiveDetector(), show_progress=False)
        return [s.seconds for s, _ in scenes][1:]   # bornes internes (on saute 0.0)
    except Exception as e:
        print(f"[v2] PySceneDetect indispo ({e}) → segmentation par visage", flush=True)
        return []

def snap_to_cuts(scenes, cuts, tol=0.6):
    """Cale les frontières de scènes (issues du visage) sur les coupures de plan réelles
    quand elles sont proches (≤ tol). Transitions plus nettes, sans changer la classification."""
    if not cuts or len(scenes) < 2:
        return scenes
    cuts = sorted(cuts)
    for i in range(1, len(scenes)):
        b = scenes[i][0]
        near = min(cuts, key=lambda c: abs(c - b))
        if abs(near - b) <= tol and scenes[i-1][0] < near < scenes[i][1]:
            scenes[i-1][1] = near
            scenes[i][0] = near
    return scenes

def segment_scenes(tl, dur, min_scene=1.3):
    """Regroupe la timeline en scènes 'pres'/'cap', lissées, durée mini."""
    if not tl:
        return [[0.0, dur, "cap", 0.5]]
    labels = [s[1] for s in tl]
    sm = labels[:]
    for i in range(1, len(labels) - 1):
        sm[i] = sorted(labels[i-1:i+2])[1]
    raw = [(t, "pres" if sm[i] else "cap", cx) for i, (t, _, cx) in enumerate(tl)]
    scenes = []
    cs_t, cs_k, cxs = raw[0][0], raw[0][1], [raw[0][2]]
    for t, k, cx in raw[1:]:
        if k == cs_k:
            cxs.append(cx)
        else:
            scenes.append([cs_t, t, cs_k, sum(cxs)/len(cxs)])
            cs_t, cs_k, cxs = t, k, [cx]
    scenes.append([cs_t, dur, cs_k, sum(cxs)/len(cxs)])
    merged = []
    for sc in scenes:
        if merged and (sc[1]-sc[0]) < min_scene:
            merged[-1][1] = sc[1]
        elif merged and merged[-1][2] == sc[2]:
            merged[-1][1] = sc[1]
        else:
            merged.append(sc)
    merged[0][0] = 0.0; merged[-1][1] = dur
    return merged

# ---------- sous-titres karaoké ----------
def ass_t(t):
    t = max(0, t); h=int(t//3600); m=int((t%3600)//60); s=t%60
    return f"{h:01d}:{m:02d}:{s:05.2f}"

def starts_apos(s):
    return bool(s) and s[0] in "'’ʼ"   # Whisper met l'apostrophe en TÊTE du mot suivant: jusqu|'à, c|'est, l|'IA

def chunk_words(ws, max_words=3, max_chars=15, max_gap=0.7):
    """Regroupe en blocs façon TikTok ; ne coupe JAMAIS avant un mot commençant par
    une apostrophe (jusqu+'à, l+'IA, c+'est restent collés dans le même bloc)."""
    chunks, cur = [], []
    for w in ws:
        glue = bool(cur) and starts_apos(w["word"])   # ce token prolonge le mot précédent
        if cur and not glue:
            gap = w["start"] - cur[-1]["end"]
            chars = sum(len(x["word"])+1 for x in cur) + len(w["word"])
            if len(cur) >= max_words or chars > max_chars or gap > max_gap:
                chunks.append(cur); cur = []
        cur.append(w)
    if cur: chunks.append(cur)
    return chunks

HL = r"{\c&H00FFFF&\fscx116\fscy116}"   # mot actif: jaune + agrandi

def build_ass(clip_start, dur, path, intro=None, intro_dur=2.8):
    ws = [{"start": w["start"]-clip_start, "end": w["end"]-clip_start, "word": w["word"]}
          for w in words_in(clip_start, clip_start+dur)]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,{FONT},82,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,6,3,2,90,90,150,1
Style: Hook,{FONT},86,&H0000FFFF,&H0000FFFF,&H00000000,&HAA000000,-1,0,0,0,100,100,0,0,4,5,0,8,70,70,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text
"""
    lines = [head]
    if intro:
        txt = intro.replace("\n", "\\N")
        lines.append(f"Dialogue: 1,{ass_t(0)},{ass_t(intro_dur)},Hook,,0,0,,{{\\fad(150,300)}}{txt}")
    for ch in ([] if NOSUBS else chunk_words(ws)):
        n = len(ch)
        for i, w in enumerate(ch):
            st = w["start"]
            en = ch[i+1]["start"] if i+1 < n else w["end"]
            disp = ""
            for j, x in enumerate(ch):
                t = x["word"].upper()
                piece = f"{HL}{t}{{\\r}}" if j == i else t
                if j == 0:
                    disp = piece
                else:
                    disp += ("" if starts_apos(x["word"]) else " ") + piece   # pas d'espace avant 'à, 'IA…
            lines.append(f"Dialogue: 0,{ass_t(st)},{ass_t(en)},Pop,,0,0,,{disp}")
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    return path

# ---------- rendu des scènes ----------
def fit_crop(rw, rh, cx):
    """Crop au ratio rw:rh, centré horizontalement sur cx (norm 0..1), aligné en haut,
    borné aux dimensions réelles de la source. Renvoie (cw, ch, x0)."""
    ch = USABLE_H
    cw = int(ch * rw / rh)
    if cw > SRC_W:
        cw = SRC_W; ch = int(cw * rh / rw)
    cw -= cw % 2; ch -= ch % 2
    x0 = int(min(max(cx * SRC_W - cw/2, 0), SRC_W - cw))
    return cw, ch, x0

ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
       "-r", "30", "-g", "60", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]

def render_presenter(abs_t0, dur, cx, out):
    cw, ch, x0 = fit_crop(W, H, cx)
    vf = f"crop={cw}:{ch}:{x0}:0,scale={W}:{H},setsar=1"
    subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",str(abs_t0),"-t",str(dur),
                    "-i",SOURCE,"-vf",vf,*ENC,out], check=True)

def render_capture(abs_t0, dur, hero, out):
    if hero:
        fc = (f"[1:v]scale={W}:{HALF},setsar=1[top];"
              f"[0:v]crop={SRC_W}:{USABLE_H}:0:0,split[a][b];"
              f"[a]scale={W}:{HALF},boxblur=22:8,setsar=1[bg];"
              f"[b]scale={W}:-2[cap];"
              f"[bg][cap]overlay=(W-w)/2:(H-h)/2[bot];"
              f"[top][bot]vstack=inputs=2[v]")
        subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",str(abs_t0),"-t",str(dur),"-i",SOURCE,
                        "-stream_loop","-1","-i",hero,
                        "-filter_complex",fc,"-map","[v]","-map","0:a","-t",str(dur),*ENC,out], check=True)
    else:
        vf = (f"[0:v]crop={SRC_W}:{USABLE_H}:0:0,split[a][b];"
              f"[a]scale={W}:{H},boxblur=26:10,setsar=1[bg];"
              f"[b]scale={W}:-2[cap];[bg][cap]overlay=(W-w)/2:(H-h)/2[v]")
        subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",str(abs_t0),"-t",str(dur),"-i",SOURCE,
                        "-filter_complex",vf,"-map","[v]","-map","0:a",*ENC,out], check=True)

def render_fit(abs_t0, dur, out):
    """Source non-paysage : remplit 1080x1920 (vidéo contenue + fond flou), pas de reframe."""
    vf = (f"[0:v]split[a][b];"
          f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=22:8,setsar=1[bg];"
          f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v]")
    subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",str(abs_t0),"-t",str(dur),"-i",SOURCE,
                    "-filter_complex",vf,"-map","[v]","-map","0:a",*ENC,out], check=True)

def extract_hero(scenes, clip_start):
    """Extrait VIDÉO du présentateur (croppé 9:8, muet) à boucler dans la moitié haute des splits."""
    pres = [s for s in scenes if s[2] == "pres"]
    if not pres:
        return None
    sc = max(pres, key=lambda s: s[1]-s[0])
    seg_dur = min(sc[1]-sc[0], 8.0)
    t0 = clip_start + sc[0]
    cw, ch, x0 = fit_crop(W, HALF, sc[3])
    hero = os.path.join(WORK, "hero.mp4")
    subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",str(t0),"-t",str(seg_dur),"-i",SOURCE,
                    "-vf",f"crop={cw}:{ch}:{x0}:0,scale={W}:{HALF},setsar=1,fps=30",
                    "-an","-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p",hero],
                   check=True)
    return hero

# ---------- pipeline par clip (isolé : un échec ne tue pas le batch) ----------
def render_clip(idx, clip):
    try:
        start, end = float(clip["start"]), float(clip["end"]); dur = end - start
    except (KeyError, ValueError, TypeError):
        print(f"[v2] clip {idx}: bornes invalides → ignoré", flush=True); return False
    if dur <= 1:
        print(f"[v2] clip {idx}: durée {dur:.1f}s trop courte → ignoré", flush=True); return False
    base = f"clip_{idx:02d}"
    print(f"\n[v2] {base}  {start:.0f}→{end:.0f} ({dur:.0f}s)  « {clip.get('title','')[:48]} »", flush=True)
    try:
        cat = os.path.join(WORK, f"{base}_cat.mp4")
        if LANDSCAPE and FIT:
            # letterbox : 16:9 entier centré + fond flou → sous-titres source larges JAMAIS coupés
            print(f"     fit (letterbox 16:9 → 9:16) sur {dur:.0f}s…", flush=True)
            render_fit(start, dur, cat)
        elif LANDSCAPE and TRACK:
            # reframe dynamique YOLO : verrouille le cadrage sur le sujet (Creator), suivi lissé
            print(f"     reframe-track (YOLO) sur {dur:.0f}s…", flush=True)
            subprocess.run([sys.executable, RF_SCRIPT, SOURCE, str(start), str(dur), cat]
                           + (["--zoom"] if TRACK_ZOOM else [])
                           + (["--center"] if TRACK_CENTER else []), check=True)
        else:
            segs = []
            if LANDSCAPE:
                tl = face_timeline(start, dur)
                scenes = segment_scenes(tl, dur)            # classification fiable par présence visage
                scenes = snap_to_cuts(scenes, shot_cuts(start, dur))   # frontières calées sur vraies coupures
                print(f"     scènes: {len(scenes)} [{'+'.join(s[2] for s in scenes)}]", flush=True)
                hero = None if FULLFRAME else extract_hero(scenes, start)
                for k, (s0, s1, kind, cx) in enumerate(scenes):
                    seg = os.path.join(WORK, f"{base}_seg{k:02d}.mp4")
                    if kind == "pres" or FULLFRAME:
                        render_presenter(start+s0, s1-s0, cx, seg)
                    else:
                        render_capture(start+s0, s1-s0, hero, seg)
                    segs.append(seg)
            else:
                seg = os.path.join(WORK, f"{base}_seg00.mp4")
                render_fit(start, dur, seg); segs.append(seg)
            lst = os.path.join(WORK, f"{base}_list.txt")
            open(lst, "w").write("".join(f"file '{os.path.abspath(s)}'\n" for s in segs))
            subprocess.run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",lst,
                            "-c","copy",cat], check=True)
        # sous-titres karaoké brûlés (+ hook d'intro si défini)
        ass = build_ass(start, dur, os.path.join(WORK, f"{base}.ass"), clip.get("intro"))
        out = os.path.join(OUTDIR, f"{base}.mp4")
        subprocess.run(["ffmpeg","-y","-loglevel","error","-i",cat,
                        "-vf",f"subtitles='{ass}':fontsdir=/usr/share/fonts",
                        "-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p",
                        "-c:a","copy",out], check=True)
        tags = " ".join(clip.get("hashtags", []))
        open(os.path.join(OUTDIR, f"{base}.txt"), "w", encoding="utf-8").write(
            f"{clip.get('title','')}\n\n{tags}\n")
        print(f"     ✅ {out}", flush=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"     ❌ clip {idx} échec rendu → ignoré ({e})", flush=True); return False

ok = 0
for i, c in enumerate(clips, 1):
    if ONLY and i != ONLY:
        continue
    if render_clip(i, c):
        ok += 1
if _MP["det"] is not None:
    try: _MP["det"].close()
    except Exception: pass
print(f"\n[v2] terminé → {OUTDIR}  ({ok} clip(s) OK)")
