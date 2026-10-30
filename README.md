# YouTube Video to Text Converter

Paste a YouTube link, get a timestamped transcript. Export as TXT, SRT, VTT or JSON.

## Run

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## How it works

1. Extracts the video ID from any `watch?v=`, `youtu.be`, `shorts`, `embed` link, or a bare ID.
2. Reads the caption track directly from YouTube (no account, no Data API key).
3. If the video has no captions, downloads the audio with `yt-dlp` and transcribes it with
   `faster-whisper` (AI speech recognition), returning the same timestamped format.
4. Optional translation of captions into other languages (uses YouTube's translation).

## Config (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | 5000 | Server port |
| `WHISPER_MODEL` | base | `tiny`, `base`, `small`, `medium`, `large-v3` (bigger = more accurate, slower) |
| `MAX_AUDIO_MINUTES` | 120 | Longest video allowed for AI transcription |

## Notes

- The AI fallback runs on CPU by default; a 10-minute video takes roughly 1-3 minutes with `base`.
- Translation applies to caption tracks only. The AI fallback returns the spoken language.
- Some cloud/datacenter IPs get blocked by YouTube. If that happens, run it locally or add a proxy.
- Use for videos you have the right to transcribe; respect YouTube's Terms of Service.
