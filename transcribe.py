#!/usr/bin/env python3
"""Transcription avec timestamps mot-par-mot via faster-whisper (CPU)."""
import sys, json, time
from faster_whisper import WhisperModel

src = sys.argv[1]                       # chemin audio/vidéo
out = sys.argv[2]                       # chemin JSON de sortie
model_size = sys.argv[3] if len(sys.argv) > 3 else "small"
lang = sys.argv[4] if len(sys.argv) > 4 else "fr"   # "auto"=détection, sinon code (fr/en…)

t0 = time.time()
print(f"[transcribe] chargement modèle '{model_size}' (CPU int8)...", flush=True)
model = WhisperModel(model_size, device="cpu", compute_type="int8")

print(f"[transcribe] transcription de {src}...", flush=True)
segments, info = model.transcribe(
    src, language=(None if lang == "auto" else lang), word_timestamps=True, vad_filter=True,
    vad_parameters=dict(min_silence_duration_ms=400),
)

data = {"language": info.language, "duration": info.duration, "segments": []}
for seg in segments:
    words = [{"start": w.start, "end": w.end, "word": w.word} for w in (seg.words or [])]
    data["segments"].append({"start": seg.start, "end": seg.end, "text": seg.text, "words": words})
    print(f"  [{seg.start:7.1f}-{seg.end:7.1f}] {seg.text.strip()[:70]}", flush=True)

with open(out, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"[transcribe] OK — {len(data['segments'])} segments, {time.time()-t0:.0f}s → {out}", flush=True)
