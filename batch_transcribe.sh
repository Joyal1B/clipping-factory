#!/usr/bin/env bash
# Transcrit le lot Creator dans un ordre priorisé (viral d'abord) — lang en, model small.
# Sous-titres karaoké nécessitent le transcript. Idempotent : saute ce qui existe déjà.
set -u
cd "$(dirname "$0")"
PY=".venv/bin/python"

# ordre priorisé : potentiel viral décroissant
ORDER=(
  "12. Creator going into a big yacht.mp4"
  "13. Creator have fun on a yacht.mp4"
  "15. Creator with David Dobrick..mp4"
  "05. Creator speak aboutTravis Scott party..mp4"
  "08. Creator doing afterparty after redcarpet.mp4"
  "16. Discours de Creator avant la plus grosse soirée de Cannes.mp4"
  "14. Creator organise the biggest Cannes festival party.mp4"
  "17. The huge party organised by Creator.mp4"
  "02_Villa tour .mp4"
  "06 Creator forget again his suit to Cannes festival..mp4"
  "10. Creator go to see his favorite DJ.mp4"
  "11. David wake up Creator to see DJ rempa.mp4"
  "01_Intro .mp4"
  "03. Guest arrived at the villa..mp4"
  "04. haircut with view Creator .mp4"
  "20. Creator sharing a fun fact.mp4"
  "18. I love Creator .mp4"
  "19. funny moment.mp4"
  "Broll Creator sport .mp4"
)

vidid () { # reproduit la normalisation de clip_local.py
  local b="${1%.*}"
  echo "$b" | sed 's/[^a-zA-Z0-9_-]\+/_/g; s/^_//; s/_$//' | cut -c1-60
}

for name in "${ORDER[@]}"; do
  src="sources/creator/$name"
  [ -f "$src" ] || { echo "[skip] introuvable: $name"; continue; }
  id=$(vidid "$name")
  trj="work/${id}.transcript.json"
  if [ -f "$trj" ]; then echo "[ok-cache] $id"; continue; fi
  echo "=== transcribe: $name → $id ==="
  $PY transcribe.py "$src" "$trj" small en || echo "[err] $name"
done
echo "=== BATCH TRANSCRIBE DONE ==="
