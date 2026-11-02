# Trend Export Whisper connector (Groq)

A Claude connector that turns Reels footage and voice notes into text, English translations and .srt subtitles.

## Tools
| Tool | What it does |
|---|---|
| `transcribe` | Speech → text in the spoken language (default Tamil) |
| `translate` | Tamil/Hindi/any speech → English text |
| `subtitles` | Timed .srt captions, English (default) or original language, short lines for vertical Reels |

Send files as a **Google Drive share link** (sharing: "Anyone with the link") or any direct file URL. Video is converted to audio on the server, so up to about an hour of footage works per request.

## One-time setup (about 10 minutes)

1. **Groq API key (free):** sign in at https://console.groq.com → API Keys → Create API Key. Copy it.
2. **GitHub:** create a new repository named `trend-export-whisper` and upload these 4 files: `server.py`, `requirements.txt`, `Dockerfile`, `render.yaml`.
3. **Render:** https://dashboard.render.com → New → Blueprint → choose the `trend-export-whisper` repo → Apply.
   - When asked for `GROQ_API_KEY`, paste the Groq key.
   - `ACCESS_TOKEN` is generated automatically. Open the service → Environment and copy its value.
4. **Your connector URL is:**
   `https://<your-render-service>.onrender.com/<ACCESS_TOKEN>/mcp`
   Keep it private. Anyone with this URL can use your Groq quota.
5. **Claude:** Settings → Connectors → Add custom connector → name it "Whisper" → paste the URL → Add.

## Notes
- Render's free plan sleeps after 15 minutes idle; the first request after that takes about a minute to wake up.
- Groq free tier allows roughly 2 hours of audio per hour and 8 hours per day, which is plenty for Reels.
- Add brand words in `context_words` (e.g. "Trend Export, Shopper Destination, Tiruppur, polo, GSM") so they are spelled correctly.
