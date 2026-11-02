"""
Whisper MCP server for Trend Export (Groq Whisper).

Tools:
  - transcribe   : audio/video link -> text in the spoken language (e.g. Tamil)
  - translate    : audio/video link -> English text (Tamil/Hindi/etc. -> English)
  - subtitles    : audio/video link -> timed .srt captions (original language or English)

Files are passed as a link (Google Drive share link or any direct URL).
Video files are converted to compressed audio with ffmpeg before upload,
so long Reels footage stays under Groq's file-size limit.
"""

import os
import re
import subprocess
import tempfile

import httpx
from fastmcp import FastMCP

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")  # secret part of the connector URL
GROQ_BASE = "https://api.groq.com/openai/v1/audio"
MODEL = "whisper-large-v3"  # supports both transcription and translation
MAX_BYTES = 24 * 1024 * 1024  # Groq free tier limit is 25 MB

mcp = FastMCP("Trend Export Whisper")


# ---------- helpers ----------

def _direct_url(link: str) -> str:
    """Turn a Google Drive share link into a direct download link."""
    m = re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?id=)([\w-]+)", link)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}&confirm=t"
    return link


def _download(link: str, folder: str) -> str:
    url = _direct_url(link)
    path = os.path.join(folder, "input_media")
    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "text/html" in ctype:
            raise ValueError(
                "The link opened a web page, not a file. For Google Drive, set sharing to "
                "'Anyone with the link' and send the file's share link."
            )
        with open(path, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return path


def _to_audio(src: str, folder: str) -> str:
    """Extract mono 16 kHz speech-quality audio (small file, best for Whisper)."""
    out = os.path.join(folder, "audio.mp3")
    cmd = ["ffmpeg", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", out]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise ValueError("Could not read audio from this file: " + res.stderr[-400:])
    if os.path.getsize(out) > MAX_BYTES:
        raise ValueError(
            "Audio is too long for one request (about 65+ minutes). Split the video and send parts."
        )
    return out


def _call_groq(endpoint: str, audio: str, language: str | None, fmt: str, prompt: str | None):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set on the server.")
    data = {"model": MODEL, "response_format": fmt, "temperature": "0"}
    if language and endpoint == "transcriptions":
        data["language"] = language
    if prompt:
        data["prompt"] = prompt
    with open(audio, "rb") as f:
        r = httpx.post(
            f"{GROQ_BASE}/{endpoint}",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            data=data,
            files={"file": ("audio.mp3", f, "audio/mpeg")},
            timeout=600,
        )
    if r.status_code != 200:
        raise ValueError(f"Groq error {r.status_code}: {r.text[:400]}")
    return r.json() if fmt == "verbose_json" else r.text


def _run(link: str, endpoint: str, language: str | None, fmt: str, prompt: str | None):
    with tempfile.TemporaryDirectory() as tmp:
        media = _download(link, tmp)
        audio = _to_audio(media, tmp)
        return _call_groq(endpoint, audio, language, fmt, prompt)


def _ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _split_long(seg_text: str, start: float, end: float, max_chars: int):
    """Break a long segment into shorter caption lines (Reels need short captions)."""
    words = seg_text.split()
    if not words:
        return []
    chunks, cur = [], []
    for w in words:
        if cur and len(" ".join(cur + [w])) > max_chars:
            chunks.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        chunks.append(" ".join(cur))
    total = sum(len(c) for c in chunks) or 1
    out, t = [], start
    for c in chunks:
        dur = (end - start) * len(c) / total
        out.append((t, t + dur, c))
        t += dur
    return out


def _to_srt(result: dict, max_chars: int) -> str:
    lines, n = [], 1
    for seg in result.get("segments", []):
        for s, e, text in _split_long(seg["text"].strip(), seg["start"], seg["end"], max_chars):
            lines.append(f"{n}\n{_ts(s)} --> {_ts(e)}\n{text}\n")
            n += 1
    return "\n".join(lines)


# ---------- tools ----------

@mcp.tool()
def transcribe(link: str, language: str = "ta", context_words: str = "") -> str:
    """Transcribe speech from an audio or video file into text in the spoken language.

    link: Google Drive share link ('Anyone with the link') or a direct file URL.
    language: ISO code of the spoken language, e.g. 'ta' Tamil, 'en' English, 'hi' Hindi.
              Use '' to auto-detect.
    context_words: optional names/terms to spell correctly, e.g. 'Trend Export, Tiruppur, polo, GSM'.
    """
    return _run(link, "transcriptions", language or None, "text", context_words or None)


@mcp.tool()
def translate(link: str, context_words: str = "") -> str:
    """Translate speech from an audio or video file (Tamil, Hindi, etc.) directly into English text.

    link: Google Drive share link ('Anyone with the link') or a direct file URL.
    context_words: optional English names/terms to spell correctly.
    """
    return _run(link, "translations", None, "text", context_words or None)


@mcp.tool()
def subtitles(link: str, output_language: str = "en", spoken_language: str = "ta",
              max_chars_per_line: int = 32, context_words: str = "") -> str:
    """Create timed .srt subtitles for a Reel or any video.

    link: Google Drive share link ('Anyone with the link') or a direct file URL.
    output_language: 'en' for English subtitles (translated), or 'original' for subtitles
                     in the spoken language (e.g. Tamil script).
    spoken_language: ISO code of the language spoken in the video (used when output is 'original').
    max_chars_per_line: shorter lines suit vertical Reels (default 32).
    context_words: optional names/terms to spell correctly.
    Returns the full .srt file content.
    """
    if output_language == "en":
        result = _run(link, "translations", None, "verbose_json", context_words or None)
    else:
        result = _run(link, "transcriptions", spoken_language or None, "verbose_json",
                      context_words or None)
    srt = _to_srt(result, max_chars_per_line)
    return srt or "No speech found in this file."


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    path = f"/{ACCESS_TOKEN}/mcp" if ACCESS_TOKEN else "/mcp"
    mcp.run(transport="http", host="0.0.0.0", port=port, path=path)
