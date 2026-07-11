#!/usr/bin/env python3
"""Sélectionne les meilleurs moments à clipper via Gemini, et génère titre + hashtags."""
import sys, json, os, urllib.request, re

TRANSCRIPT = sys.argv[1]
OUT        = sys.argv[2]
N          = int(sys.argv[3]) if len(sys.argv) > 3 else 6
MODEL      = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# clé depuis .env ou env
KEY = os.environ.get("GEMINI_API_KEY")
if not KEY and os.path.exists(os.path.join(os.path.dirname(__file__), ".env")):
    for line in open(os.path.join(os.path.dirname(__file__), ".env")):
        if line.startswith("GEMINI_API_KEY"):
            KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
if not KEY:
    sys.exit("ERREUR: GEMINI_API_KEY manquante (env ou .env)")

tr = json.load(open(TRANSCRIPT, encoding="utf-8"))
# transcript indexé par timestamps pour le prompt
lines = []
for seg in tr["segments"]:
    lines.append(f"[{seg['start']:.1f}-{seg['end']:.1f}] {seg['text'].strip()}")
transcript_txt = "\n".join(lines)

PROMPT = f"""Tu es un expert du clipping viral (TikTok / Reels / Shorts) en français.
Voici la transcription horodatée d'une vidéo. Sélectionne les {N} MEILLEURS moments à transformer en clips courts viraux.

Critères d'un bon clip:
- 20 à 60 secondes, autonome (compréhensible sans contexte)
- commence sur un HOOK fort (question choc, affirmation forte, chiffre, promesse)
- une idée claire, une punchline ou une révélation
- évite les passages mous, les transitions, les "euh"

Pour chaque clip donne:
- start, end : timestamps en secondes (alignés sur des débuts/fins de phrase)
- title : titre accrocheur en français (max 70 caractères, style TikTok, sans guillemets)
- hook_reason : pourquoi ça marche (1 phrase)
- viral_score : note /10
- hashtags : 4 à 6 hashtags pertinents en français (avec #)

Réponds UNIQUEMENT en JSON valide: une liste d'objets. Pas de texte autour.

TRANSCRIPTION:
{transcript_txt}
"""

url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}"
body = {
    "contents": [{"parts": [{"text": PROMPT}]}],
    "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"},
}
req = urllib.request.Request(url, data=json.dumps(body).encode(),
                             headers={"Content-Type": "application/json"})
print(f"[detect] appel {MODEL}...", flush=True)
resp = json.load(urllib.request.urlopen(req, timeout=120))
text = resp["candidates"][0]["content"]["parts"][0]["text"]

# parse robuste
m = re.search(r"\[.*\]", text, re.S)
clips = json.loads(m.group(0) if m else text)
clips = sorted(clips, key=lambda c: c.get("viral_score", 0), reverse=True)

json.dump(clips, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"[detect] {len(clips)} clips sélectionnés → {OUT}")
for c in clips:
    print(f"  {c.get('viral_score','?')}/10  [{c['start']:.0f}-{c['end']:.0f}]  {c.get('title','')}")
