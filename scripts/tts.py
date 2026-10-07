#!/usr/bin/env python3
"""Generate the daily voiceover with ElevenLabs and word-level timings.

Usage: python3 scripts/tts.py <dir>
Reads  <dir>/request.json  {"id", "text", "voice_id", "model_id"}
Writes <dir>/voice.mp3, <dir>/words.json, <dir>/result.json
Needs  ELEVENLABS_API_KEY in the environment (a GitHub Actions secret).
The key is only ever read from the environment; it is never written to disk or logged.
"""
import base64, json, os, subprocess, sys, urllib.error, urllib.request

d = sys.argv[1] if len(sys.argv) > 1 else "vo"

def done(status, **kw):
    json.dump({"status": status, **kw}, open(os.path.join(d, "result.json"), "w"), indent=2)
    print(status.upper(), kw.get("reason", ""))
    sys.exit(0 if status == "ok" else 1)

key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
if not key:
    done("failed", reason="ELEVENLABS_API_KEY secret is not set on the repository")
try:
    req = json.load(open(os.path.join(d, "request.json")))
except Exception as e:
    done("failed", reason=f"request.json unreadable: {e}")
text = (req.get("text") or "").strip()
voice = req.get("voice_id") or "MlIxnl4hUPbFzWffsZ76"
model = req.get("model_id") or "eleven_multilingual_v2"
if not text:
    done("failed", reason="request.json has no text")
if len(text) > 2000:
    done("failed", reason=f"text too long ({len(text)} chars)")

url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128"
body = json.dumps({"text": text, "model_id": model}).encode()
r = urllib.request.Request(url, data=body, method="POST",
                           headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "application/json"})
try:
    with urllib.request.urlopen(r, timeout=180) as resp:
        data = json.load(resp)
except urllib.error.HTTPError as e:
    detail = e.read().decode("utf-8", "replace")[:400]
    done("failed", reason=f"ElevenLabs HTTP {e.code}: {detail}")
except Exception as e:
    done("failed", reason=f"ElevenLabs request failed: {e}")

open(os.path.join(d, "voice.mp3"), "wb").write(base64.b64decode(data["audio_base64"]))

al = data.get("alignment") or data.get("normalized_alignment") or {}
chars = al.get("characters", [])
st = al.get("character_start_times_seconds", [])
en = al.get("character_end_times_seconds", [])
words, cur, s0, e0 = [], "", None, None
for c, s, e in zip(chars, st, en):
    if c.isspace():
        if cur:
            words.append({"text": cur, "start": round(s0, 3), "end": round(e0, 3)})
        cur, s0 = "", None
        continue
    if s0 is None:
        s0 = s
    cur += c
    e0 = e
if cur:
    words.append({"text": cur, "start": round(s0, 3), "end": round(e0, 3)})
json.dump(words, open(os.path.join(d, "words.json"), "w"))

dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                      os.path.join(d, "voice.mp3")], capture_output=True, text=True).stdout.strip()
done("ok", id=req.get("id"), voice_id=voice, model_id=model, duration_seconds=float(dur or 0), word_count=len(words))
