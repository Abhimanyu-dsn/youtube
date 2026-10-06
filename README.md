# Daily Shorts pipeline

Public relay for the daily AI design Shorts.

1. The scheduled agent renders a silent 1080×1920 master timed to an ElevenLabs voiceover and pushes it to a `job/<id>` branch with a `job.json` pointing at the voiceover.
2. `.github/workflows/merge-short.yml` downloads the voiceover, merges it (`scripts/merge.sh`), checks size and audio, and publishes the result as release `short-<id>`, then deletes the branch.
3. The agent passes the release's `final.mp4` URL to Metricool, which schedules the upload to YouTube.

Everything here is public, including each video before it goes live on YouTube.
