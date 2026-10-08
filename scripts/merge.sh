#!/usr/bin/env bash
# Merge the ElevenLabs voiceover into the silent master and verify the result.
# Usage: scripts/merge.sh <job-dir>   (expects job.json and video.mp4 inside)
# Always writes <job-dir>/result.json; writes <job-dir>/final.mp4 on success.
set -uo pipefail

DIR="${1:-job}"
cd "$DIR" || exit 1

fail() {
  jq -n --arg reason "$1" '{status: "failed", reason: $reason}' > result.json
  echo "FAILED: $1" >&2
  exit 1
}

dur() { ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$1" | head -1 | tr -cd 0-9.; }

[ -f job.json ] || fail "job.json missing"
[ -f video.mp4 ] || fail "video.mp4 missing"
AUDIO_URL="$(jq -r '.audio_url // empty' job.json)"
[ -n "$AUDIO_URL" ] || fail "audio_url missing in job.json"

curl -fsSL --retry 3 --retry-delay 5 -o voice.audio "$AUDIO_URL" || fail "could not download voiceover"

VD="$(dur video.mp4)" || fail "video.mp4 unreadable"
AD="$(dur voice.audio)" || fail "voiceover unreadable"

# Audio must not run past the video; the video may run longer (pad with silence).
python3 - "$VD" "$AD" <<'PY' || fail "voiceover (${AD}s) is longer than the video (${VD}s)"
import sys
v, a = map(float, sys.argv[1:3])
sys.exit(0 if a <= v + 0.25 else 1)
PY

ffmpeg -v error -y -i video.mp4 -i voice.audio \
  -filter_complex "[1:a]aresample=48000,apad[a]" \
  -map 0:v:0 -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest \
  -movflags +faststart final.mp4 || fail "ffmpeg merge failed"

W="$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of default=nw=1:nk=1 final.mp4 | head -1 | tr -cd 0-9)"
H="$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of default=nw=1:nk=1 final.mp4 | head -1 | tr -cd 0-9)"
HAS_AUDIO="$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 final.mp4 | head -1)"
FD="$(dur final.mp4)"

[ "$W" = "1080" ] && [ "$H" = "1920" ] || { rm -f final.mp4; fail "final video is ${W}x${H}, expected 1080x1920"; }
[ -n "$HAS_AUDIO" ] || { rm -f final.mp4; fail "final video has no audio stream"; }

jq -n --arg vd "$VD" --arg ad "$AD" --arg fd "$FD" \
  '{status: "ok", video_seconds: ($vd|tonumber), voice_seconds: ($ad|tonumber), final_seconds: ($fd|tonumber), width: 1080, height: 1920}' > result.json
echo "OK: final.mp4 ${FD}s"
