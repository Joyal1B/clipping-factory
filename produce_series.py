#!/usr/bin/env python3
"""Produit la série de clips Creator (Vlog Cannes) → clips_v2/serie/.
Chaque entrée : source, bornes, hook (intro, SANS emoji pour libass), titre (.txt, emoji OK),
mode de cadrage (track YOLO sur sujet continu / center pour montages multi-plans),
nosubs (clips à sous-titres source incrustés : on ne brûle que le hook).

usage: produce_series.py [--only 12] [--list]
"""
import sys, os, re, json, subprocess, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
PY   = os.path.join(HERE, ".venv", "bin", "python")
SRC  = os.path.join(HERE, "sources", "creator")
OUT  = os.path.join(HERE, "clips_v2", "serie"); os.makedirs(OUT, exist_ok=True)

def vidid(name):
    b = os.path.splitext(name)[0]
    return re.sub(r'[^a-zA-Z0-9_-]+', '_', b).strip('_')[:60] or "clip"

TAGS_BASE = ["#creator", "#cannes", "#fyp", "#foryou"]
def tags(*extra):
    seen, out = set(), []
    for t in list(extra) + TAGS_BASE:
        if t not in seen:
            seen.add(t); out.append(t)
    return out

# n=numéro source · file=nom fichier · slug=sortie · mode=track|center · nosubs=bool
PRODS = [
 {"n":1, "file":"01_Intro .mp4", "slug":"intro_500k", "mode":"fit", "nosubs":True,
  "start":0.0, "end":26.0,
  "intro":"POV: a $500K week in Cannes",
  "title":"A $500,000 week in Cannes 🎬🔥",
  "hashtags":tags("#luxurylifestyle","#millionaire","#entrepreneur","#creator")},

 {"n":2, "file":"02_Villa tour .mp4", "slug":"villa_tour", "mode":"fit", "nosubs":True,
  "start":0.0, "end":30.0,
  "intro":"Touring an insane Cannes villa",
  "title":"Inside an insane Cannes villa 🏛️ — secret room, gym, elevator",
  "hashtags":tags("#villa","#luxuryhomes","#mansion","#luxurylifestyle")},

 {"n":5, "file":"05. Creator speak aboutTravis Scott party..mp4", "slug":"travis_scott", "mode":"center", "nosubs":True,
  "start":0.0, "end":23.5,
  "intro":"$100,000 to party with Travis Scott",
  "title":"$100K to party with Travis Scott in Cannes 🎤🔥",
  "hashtags":tags("#travisscott","#party","#luxurylifestyle")},

 {"n":6, "file":"06 Creator forget again his suit to Cannes festival..mp4", "slug":"forgot_tuxedo", "mode":"track", "nosubs":False,
  "start":0.0, "end":18.5,
  "intro":"Forgot my tuxedo... 3rd year in a row",
  "title":"Forgot my tuxedo for the Cannes red carpet again 😅",
  "hashtags":tags("#redcarpet","#monteedesmarches","#funny")},

 {"n":12, "file":"12. Creator going into a big yacht.mp4", "slug":"yacht_pullup", "mode":"track", "nosubs":True,
  "start":8.0, "end":33.0,
  "intro":"POV: invited onto a 45m yacht in Cannes",
  "title":"Pulling up to a 45m yacht in Cannes 🛥️",
  "hashtags":tags("#yacht","#luxurylifestyle","#millionaire","#summer")},

 {"n":13, "file":"13. Creator have fun on a yacht.mp4", "slug":"yacht_day", "mode":"track", "nosubs":True,
  "start":32.0, "end":62.0,
  "intro":"A day on a yacht in Cannes hits different",
  "title":"A day on a yacht in Cannes 🛥️☀️",
  "hashtags":tags("#yacht","#summer","#luxurylifestyle","#jetski")},

 {"n":14, "file":"14. Creator organise the biggest Cannes festival party.mp4", "slug":"secret_party", "mode":"track", "nosubs":False,
  "start":0.0, "end":18.5,
  "intro":"Throwing a Cannes party the police can't shut down",
  "title":"How to throw a secret party in Cannes 🤫",
  "hashtags":tags("#party","#entrepreneur","#cannesfestival")},

 {"n":15, "file":"15. Creator with David Dobrick..mp4", "slug":"david_dobrik", "mode":"track", "nosubs":False,
  "start":87.5, "end":103.5,
  "intro":"Teaching David Dobrik a French greeting",
  "title":"I taught David Dobrik a French phrase 😂",
  "hashtags":tags("#daviddobrik","#funny","#comedy")},

 {"n":17, "file":"17. The huge party organised by Creator.mp4", "slug":"biggest_party", "mode":"track", "nosubs":True,
  "start":38.0, "end":54.0,
  "intro":"I DJ'd my own party in Cannes",
  "title":"I threw the biggest party in Cannes and DJ'd it myself 🎧🔥",
  "hashtags":tags("#party","#dj","#keinemusik","#luxurylifestyle")},

 {"n":20, "file":"20. Creator sharing a fun fact.mp4", "slug":"first_party_story", "mode":"track", "nosubs":False,
  "start":0.0, "end":54.0,
  "intro":"How I threw my first party with $0",
  "title":"How I threw my first party with $0 and Facebook ads 📈",
  "hashtags":tags("#entrepreneur","#marketing","#business","#story")},

 {"n":11, "file":"11. David wake up Creator to see DJ rempa.mp4", "slug":"rampa_breakfast", "mode":"fit", "nosubs":True,
  "start":0.0, "end":31.0,
  "intro":"Waking up Creator: a Keinemusik DJ is here",
  "title":"Rampa (Keinemusik) pulled up to the villa for breakfast 🎧",
  "hashtags":tags("#keinemusik","#rampa","#dj")},
]

ONLY = None
if "--only" in sys.argv:
    ONLY = int(sys.argv[sys.argv.index("--only")+1])
if "--list" in sys.argv:
    for p in PRODS:
        print(f"  #{p['n']:>2} {p['slug']:18} {p['mode']:6} {'NOSUB' if p['nosubs'] else 'subs ':5} "
              f"{p['start']:.0f}-{p['end']:.0f}s  « {p['intro']} »")
    sys.exit(0)

def run(cmd, env=None):
    subprocess.run(cmd, check=True, env=env)

done, fail = [], []
for p in PRODS:
    if ONLY and p["n"] != ONLY:
        continue
    src = os.path.join(SRC, p["file"])
    if not os.path.exists(src):
        print(f"[!] source absente: {p['file']}"); fail.append(p["n"]); continue
    vid = vidid(p["file"])
    trj = os.path.join(HERE, "work", f"{vid}.transcript.json")
    if not os.path.exists(trj):
        print(f"[!] transcript absent pour #{p['n']} ({vid}) → saut"); fail.append(p["n"]); continue
    clj = os.path.join(HERE, "work", f"{vid}.clips.json")
    json.dump([{ "start":p["start"], "end":p["end"], "intro":p["intro"],
                 "title":p["title"], "hashtags":p["hashtags"] }],
              open(clj, "w", encoding="utf-8"), ensure_ascii=False)
    rdir = os.path.join(HERE, "work", "render", vid)
    shutil.rmtree(rdir, ignore_errors=True); os.makedirs(rdir, exist_ok=True)
    env = dict(os.environ)
    env["CLIP_TRACK"] = "1"
    env["CLIP_FULLFRAME"] = "1"
    if p["mode"] == "center":
        env["CLIP_TRACK_CENTER"] = "1"
    elif p["mode"] == "fit":
        env["CLIP_FIT"] = "1"
    if p["nosubs"]:
        env["CLIP_NOSUBS"] = "1"
    print(f"\n========== #{p['n']} {p['slug']} ({p['mode']}, {'nosubs' if p['nosubs'] else 'subs'}) "
          f"{p['start']:.0f}-{p['end']:.0f}s ==========", flush=True)
    try:
        run([PY, os.path.join(HERE, "render_v2.py"), trj, clj, src, rdir], env=env)
    except subprocess.CalledProcessError as e:
        print(f"[X] échec rendu #{p['n']}: {e}"); fail.append(p["n"]); continue
    produced = os.path.join(rdir, "clip_01.mp4")
    if not os.path.exists(produced):
        print(f"[X] pas de sortie pour #{p['n']}"); fail.append(p["n"]); continue
    dst = os.path.join(OUT, f"creator_{p['n']:02d}_{p['slug']}.mp4")
    shutil.copy(produced, dst)
    txt = os.path.join(rdir, "clip_01.txt")
    if os.path.exists(txt):
        shutil.copy(txt, dst[:-4] + ".txt")
    print(f"[✓] → {dst}", flush=True)
    done.append(p["n"])

print(f"\n=== SÉRIE TERMINÉE — OK: {done} · échecs: {fail} ===")
print(f"=== Sorties dans {OUT}/ ===")
