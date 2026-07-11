#!/usr/bin/env python3
"""Reframe dynamique 9:16 avec suivi de SILHOUETTE (YOLO + ByteTrack).

Garde le focus sur le sujet principal (Creator) même de dos / de loin / dans la foule :
  1. YOLO détecte+suit les personnes (IDs persistants) sur le segment
  2. identifie le sujet = track au meilleur score médian (aire × netteté × centralité)
  3. trajectoire cx(t) interpolée + lissée (mouvement de caméra doux, pas de saccade)
  4. crop 9:16 hauteur-pleine qui suit le sujet → scale 1080x1920, audio d'origine réattaché

usage: reframe_track.py <source.mp4> <start> <dur> <out.mp4> [--model yolo11n.pt] [--zoom]
"""
import sys, os, subprocess, json
import numpy as np, cv2

SRC, START, DUR, OUT = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
def opt(name, d):
    return sys.argv[sys.argv.index(name)+1] if name in sys.argv else d
YOLO_MODEL = opt("--model", "yolo11n.pt")
ZOOM = "--zoom" in sys.argv          # zoom adaptatif si sujet petit (sinon hauteur pleine)
CENTER = "--center" in sys.argv      # crop centré fixe (montage multi-plans / sous-titres source centrés)
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work"); os.makedirs(WORK, exist_ok=True)
OUT_W, OUT_H = 1080, 1920
AR = OUT_W / OUT_H                    # largeur/hauteur du crop = 9/16

# 1. extraire le segment source (résolution native, avec audio)
seg = os.path.join(WORK, "_rf_seg.mp4")
subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",str(START),"-t",str(DUR),
                "-i",SRC,"-c","copy",seg], check=False)
if not os.path.exists(seg) or os.path.getsize(seg) < 1000:
    subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",str(START),"-t",str(DUR),
                    "-i",SRC,"-c:v","libx264","-preset","veryfast","-crf","18","-c:a","aac",seg], check=True)

cap = cv2.VideoCapture(seg)
FPS = cap.get(cv2.CAP_PROP_FPS) or 30.0
NF  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
W   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"[rf] segment {W}x{H} {FPS:.1f}fps {NF}f", flush=True)

def sharpness(crop):
    if crop.size == 0: return 0.0
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())

# 2. détection du sujet — sauf en mode --center (crop vertical centré fixe, sous-titres source préservés)
if CENTER:
    cap.release()
    print("[rf] mode --center : crop vertical centré fixe", flush=True)
    tracks = {}
else:
    from ultralytics import YOLO
    model = YOLO(YOLO_MODEL)
    STEP = max(1, int(round(FPS/6)))     # ~6 détections/s
    tracks = {}                          # id -> list de (frame_idx, cx, cy, bw, bh, score)
    fi = 0
    ok, frame = cap.read()
    while ok:
        if fi % STEP == 0:
            res = model.track(frame, classes=[0], conf=0.35, persist=True,
                              tracker="bytetrack.yaml", verbose=False)[0]
            if res.boxes is not None and res.boxes.id is not None:
                for b, tid in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.id.cpu().numpy().astype(int)):
                    x1,y1,x2,y2 = b
                    bw, bh = x2-x1, y2-y1
                    cx, cy = (x1+x2)/2, (y1+y2)/2
                    area = (bw*bh)/(W*H)
                    sub = frame[int(max(0,y1)):int(y2), int(max(0,x1)):int(x2)]
                    shp = sharpness(sub)
                    centr = 1.0 - abs(cx/W - 0.5)*2*0.5      # léger bonus centralité
                    score = area * (1+shp/500.0) * centr
                    tracks.setdefault(tid, []).append((fi, cx, cy, bw, bh, score))
        fi += 1
        ok, frame = cap.read()
    cap.release()

if not tracks:
    print("[rf] aucun sujet détecté → crop centré", flush=True)
    traj = {f: (W/2, H/2, H) for f in range(NF)}
else:
    # 3. sujet = track au meilleur score médian, pondéré par durée de présence
    def track_score(samples):
        scores = [s[5] for s in samples]
        return float(np.median(scores)) * (len(samples) ** 0.5)
    hero_id = max(tracks, key=lambda t: track_score(tracks[t]))
    pts = sorted(tracks[hero_id])
    print(f"[rf] sujet = track #{hero_id} ({len(pts)} obs sur {len(tracks)} pers.)", flush=True)
    # trajectoire éparse → interpolation dense par frame
    fis = np.array([p[0] for p in pts]);
    cxs = np.array([p[1] for p in pts]); cys = np.array([p[2] for p in pts])
    bhs = np.array([p[4] for p in pts])
    allf = np.arange(NF)
    cx_d = np.interp(allf, fis, cxs); cy_d = np.interp(allf, fis, cys); bh_d = np.interp(allf, fis, bhs)
    # 4. lissage temporel (moyenne mobile ~0.5s) = mouvement de caméra doux
    k = max(3, int(FPS*0.5)) | 1
    ker = np.ones(k)/k
    pad = k//2
    sm = lambda a: np.convolve(np.pad(a,(pad,pad),mode='edge'), ker, 'valid')
    cx_s, cy_s, bh_s = sm(cx_d), sm(cy_d), sm(bh_d)
    traj = {f: (cx_s[f], cy_s[f], bh_s[f]) for f in range(NF)}

# 5. crop 9:16 dynamique frame-by-frame
tmp = os.path.join(WORK, "_rf_vertical.mp4")
vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (OUT_W, OUT_H))
cap = cv2.VideoCapture(seg)
fi = 0
ok, frame = cap.read()
while ok:
    cx, cy, bh = traj.get(fi, (W/2, H/2, H))
    crop_h = H
    crop_w = int(round(crop_h * AR))
    if ZOOM and bh > 0:                  # zoom adaptatif: sujet ~70% de la hauteur
        target_h = min(H, max(crop_w, bh/0.7))
        crop_h = int(round(target_h)); crop_w = int(round(crop_h*AR))
    x0 = int(round(cx - crop_w/2)); y0 = int(round(cy - crop_h/2))
    x0 = max(0, min(W-crop_w, x0));  y0 = max(0, min(H-crop_h, y0))
    crop = frame[y0:y0+crop_h, x0:x0+crop_w]
    vw.write(cv2.resize(crop, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA))
    fi += 1
    ok, frame = cap.read()
cap.release(); vw.release()

# 6. réattacher l'audio d'origine
subprocess.run(["ffmpeg","-y","-loglevel","error","-i",tmp,"-i",seg,
                "-map","0:v","-map","1:a?","-c:v","libx264","-preset","veryfast","-crf","20",
                "-pix_fmt","yuv420p","-c:a","aac","-shortest",OUT], check=True)
print(f"[rf] ✅ {OUT}", flush=True)
