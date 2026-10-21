#!/usr/bin/env python3
"""Free-voice fallback: generate the voiceover with Kokoro (open-source, Apache-2.0).

Usage: python3 scripts/tts_kokoro.py <dir> [fallback_reason]
Reads  <dir>/request.json  {"id", "text", ...}
Writes <dir>/voice.mp3, <dir>/words.json, <dir>/result.json (provider "kokoro")

tts.py calls this automatically when ElevenLabs reports a quota/credit error.
Voice af_heart at 1.1x. Each phrase (split on , . : ; ? !) is synthesised on its
own so pauses are known exactly; word timings inside a phrase are estimated from
word length. No API key is needed.
"""
import json, os, re, subprocess, sys, urllib.request

d = sys.argv[1] if len(sys.argv) > 1 else "vo"
fallback_reason = sys.argv[2] if len(sys.argv) > 2 else ""
VOICE, SPEED, SR = "af_heart", 1.1, 24000
MODEL_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
CACHE = os.path.expanduser("~/.cache/kokoro")


def done(status, **kw):
    if fallback_reason:
        kw["fallback_reason"] = fallback_reason
    json.dump({"status": status, "provider": "kokoro", **kw}, open(os.path.join(d, "result.json"), "w"), indent=2)
    print(status.upper(), kw.get("reason", ""))
    sys.exit(0 if status == "ok" else 1)


try:
    req = json.load(open(os.path.join(d, "request.json")))
    text = (req.get("text") or "").strip()
    if not text:
        done("failed", reason="request.json has no text")

    try:
        import numpy as np, soundfile as sf
        from kokoro_onnx import Kokoro
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "kokoro-onnx", "soundfile"], check=True)
        import numpy as np, soundfile as sf
        from kokoro_onnx import Kokoro

    os.makedirs(CACHE, exist_ok=True)
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        p = os.path.join(CACHE, f)
        if not os.path.exists(p) or os.path.getsize(p) < 1_000_000:
            urllib.request.urlretrieve(MODEL_BASE + f, p)
    k = Kokoro(os.path.join(CACHE, "kokoro-v1.0.onnx"), os.path.join(CACHE, "voices-v1.0.bin"))

    chunks = [c.strip() for c in re.findall(r"[^,.:;?!]+[,.:;?!]*", text) if c.strip()]

    def trim(a, th=0.008):
        idx = np.where(np.abs(a) > th)[0]
        return a[max(0, idx[0] - int(0.02 * SR)): idx[-1] + int(0.04 * SR)] if len(idx) else a

    parts, words, t = [np.zeros(int(0.08 * SR), dtype=np.float32)], [], 0.08
    for c in chunks:
        s, _ = k.create(c, voice=VOICE, speed=SPEED, lang="en-us")
        s = trim(np.asarray(s, dtype=np.float32))
        dur = len(s) / SR
        ws = c.split()
        weights = [len(re.sub(r"[^A-Za-z0-9]", "", w)) + 2 for w in ws]
        tot, cur, span = sum(weights), t + 0.03, max(0.05, dur - 0.07)
        for w, wt in zip(ws, weights):
            dw = span * wt / tot
            words.append({"text": w, "start": round(cur, 3), "end": round(cur + dw, 3)})
            cur += dw
        parts.append(s)
        t += dur
        gap = 0.12 if c[-1] in ",;" else (0.30 if c[-1] in ".:?!" else 0.08)
        parts.append(np.zeros(int(gap * SR), dtype=np.float32))
        t += gap

    wav = os.path.join(d, "voice_raw.wav")
    sf.write(wav, np.concatenate(parts), SR)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-ar", "44100", "-b:a", "192k", os.path.join(d, "voice.mp3")], check=True)
    os.remove(wav)
    json.dump(words, open(os.path.join(d, "words.json"), "w"))

    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          os.path.join(d, "voice.mp3")], capture_output=True, text=True).stdout.strip()
    if float(dur or 0) < 1:
        done("failed", reason="Kokoro produced no audio")
    done("ok", id=req.get("id"), voice_id=f"kokoro:{VOICE}", model_id="kokoro-v1.0", speed=SPEED,
         duration_seconds=float(dur), word_count=len(words), timing="estimated within phrases")
except SystemExit:
    raise
except Exception as e:
    done("failed", reason=f"Kokoro fallback failed: {e}")
