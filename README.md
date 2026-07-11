# Clipping Factory

> **Turn long-form video into viral 9:16 shorts — automatically.**
> Transcribe → pick the best moments → cut → **silhouette-tracking reframe** → adaptive render with word-level karaoke subtitles.

![python](https://img.shields.io/badge/python-3.10%2B-36e0ff?labelColor=0b1220) ![yolo](https://img.shields.io/badge/reframe-YOLO11%20%2B%20ByteTrack-8b5cf6?labelColor=0b1220) ![asr](https://img.shields.io/badge/ASR-faster--whisper-36e0ff?labelColor=0b1220) ![status](https://img.shields.io/badge/status-production-brightgreen?labelColor=0b1220)

A CPU-friendly pipeline that takes a long video and ships vertical clips ready for TikTok / Reels / Shorts. The reframe engine **keeps the subject centered even when they turn away, walk into a crowd, or move across the frame** — no manual keyframing.

---

## Pipeline

```
 long video ──▶ transcribe ──▶ select moments ──▶ cut ──▶ reframe 9:16 ──▶ render ──▶ short
 (url / file)   word-level      hooks + titles           silhouette        adaptive
                faster-whisper                            YOLO + ByteTrack  layout + subs
```

## Scripts

| Script | Role |
|---|---|
| `clip.py` | Entry point (URL): download + transcribe, then show the transcript for moment selection. |
| `clip_local.py` | Same for a **local file** (no URL/download). |
| `transcribe.py` | Word-level timestamps via **faster-whisper** (CPU). |
| `detect.py` | Suggests the best moments to clip + generates title & hashtags. |
| `make_clips.py` | Cut + 9:16 reframe + burned-in animated subtitles from a transcript + clip list. |
| `reframe_track.py` | **Dynamic 9:16 reframe** with silhouette tracking (YOLO + ByteTrack) — persistent subject focus. |
| `render_v2.py` | Adaptive render engine: face-track fullframe / 50-50 split + karaoke subtitles, resilient per-clip (one failure never kills the batch). |
| `produce_series.py` | Batch a whole series with per-clip framing modes. |
| `batch_transcribe.sh` | Transcribe a batch in priority order (idempotent — skips what already exists). |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**System deps** (not pip): [`ffmpeg`](https://ffmpeg.org/) and [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) for URL downloads.
**Model weights**: the YOLO `.pt` file downloads automatically on first run (via `ultralytics`).

## Usage

```bash
# 1) download + transcribe (URL) — then inspect the transcript
python clip.py "https://…"

# local file variant
python clip_local.py video.mp4 --lang en --model small

# 2) render the selected clips (9:16, subtitles, subject tracking)
CLIP_TRACK=1 python render_v2.py work/<id>.transcript.json work/<id>.clips.json
```

Behavior is tuned via env vars (`WHISPER_MODEL`, `CLIP_FONT`, `CLIP_TRACK`, `CLIP_FULLFRAME`, `CLIP_FIT`, `CLIP_NOSUBS`, …).

---

<sub>Built by **Sam The SpaceJoker** · [NullAgency.on](https://nullagency.online) — shared as a showcase. No credentials, no third-party content in this repo.</sub>
