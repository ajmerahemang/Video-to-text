"""YouTube Video to Text Converter - backend.

Run:  python app.py   ->  http://localhost:5000
"""
import glob
import os
import re
import shutil
import tempfile

from flask import Flask, jsonify, request, send_from_directory
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
MAX_AUDIO_MINUTES = int(os.environ.get("MAX_AUDIO_MINUTES", "120"))
_model = None

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
URL_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/|v/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)


def extract_id(text: str):
    text = (text or "").strip()
    if ID_RE.match(text):
        return text
    m = URL_RE.search(text)
    return m.group(1) if m else None


def get_captions(vid: str, lang: str, translate: str):
    """Pull the caption track straight from YouTube."""
    api = YouTubeTranscriptApi()
    tlist = api.list(vid)
    transcript = None
    wanted = lang or "en"
    try:
        transcript = tlist.find_transcript([wanted])
    except NoTranscriptFound:
        transcript = next(iter(tlist))  # first available track
    if translate and transcript.is_translatable and translate != transcript.language_code:
        transcript = transcript.translate(translate)
    fetched = transcript.fetch()
    segs = [
        {"start": round(s.start, 2), "duration": round(s.duration, 2), "text": s.text}
        for s in fetched
    ]
    return segs, getattr(transcript, "language_code", wanted)


def whisper_transcribe(vid: str):
    """Fallback for videos without captions: download audio + AI speech recognition."""
    global _model
    import yt_dlp
    from faster_whisper import WhisperModel

    tmp = tempfile.mkdtemp(prefix="yt2txt_")
    try:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmp, "audio.%(ext)s"),
            "quiet": True,
            "noplaylist": True,
        }
        url = f"https://www.youtube.com/watch?v={vid}"
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if (info.get("duration") or 0) > MAX_AUDIO_MINUTES * 60:
                raise ValueError(
                    f"Video is longer than {MAX_AUDIO_MINUTES} minutes; "
                    "raise MAX_AUDIO_MINUTES to allow it."
                )
            ydl.download([url])
        files = glob.glob(os.path.join(tmp, "audio.*"))
        if not files:
            raise RuntimeError("Audio download failed.")
        if _model is None:
            _model = WhisperModel(WHISPER_MODEL, compute_type="int8")
        segments, info = _model.transcribe(files[0], vad_filter=True)
        out = [
            {
                "start": round(s.start, 2),
                "duration": round(s.end - s.start, 2),
                "text": s.text.strip(),
            }
            for s in segments
            if s.text.strip()
        ]
        return out, info.language
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    return send_from_directory(BASE, "manifest.webmanifest", mimetype="application/manifest+json")


@app.get("/icon.svg")
def icon():
    return send_from_directory(BASE, "icon.svg", mimetype="image/svg+xml")


@app.get("/sw.js")
def sw():
    return send_from_directory(BASE, "sw.js", mimetype="text/javascript")


@app.post("/api/transcript")
def transcript():
    data = request.get_json(silent=True) or {}
    vid = extract_id(data.get("url", ""))
    if not vid:
        return jsonify(error="That doesn't look like a YouTube link or video ID."), 400
    lang = (data.get("lang") or "").strip()
    translate = (data.get("translate") or "").strip()

    try:
        segs, language = get_captions(vid, lang, translate)
        return jsonify(video_id=vid, language=language, source="captions", segments=segs)
    except (TranscriptsDisabled, NoTranscriptFound, StopIteration):
        pass  # no captions -> fall through to speech recognition
    except Exception as e:  # unavailable / private / blocked etc.
        return jsonify(error=f"Could not read this video: {type(e).__name__}"), 502

    try:
        segs, language = whisper_transcribe(vid)
        return jsonify(video_id=vid, language=language, source="ai", segments=segs)
    except ImportError:
        return jsonify(
            error="No captions on this video. Install yt-dlp and faster-whisper "
            "(see README) to enable AI transcription."
        ), 501
    except Exception as e:
        return jsonify(error=f"AI transcription failed: {e}"), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
