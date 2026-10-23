# Demo video pipeline

One command re-records everything on the local stack:

```sh
scripts/video/make.sh              # reset demo → build web → TTS → record all scenes → assemble
SKIP_TTS=1 scripts/video/make.sh   # reuse narration audio
scripts/video/make.sh 08-proposal  # re-record some scenes only (no reset), then re-assemble
```

| File | Role |
|---|---|
| `narration.json` / `teaser.json` | Voiceover text per scene and the teaser line + cut list |
| `tts.py` | OpenAI TTS (`gpt-4o-mini-tts`); regenerates only lines whose text changed |
| `record.mjs` | Playwright, 1920×1080, one WebM per scene, injected cursor overlay |
| `assemble.mjs` | Title cards and burned-in captions rendered as PNG (brand fonts), composited with ffmpeg; H.264 + AAC, faststart |
| `make.sh` | Orchestrates the above; starts/stops its own API (:8000), worker and isolated web build (:3320) |

Outputs (gitignored): `docs/delivery/video/igs-os-demo.mp4`, `igs-os-teaser.mp4`; intermediates in `build/video/`.

Notes
- The approval scene approves IGS-2711 for real (a live Temporal workflow resumes), so a full run
  always resets the demo first (`services/core/scripts/demo_reset.py`).
- The copilot scene uses the scripted fake transport (`NEXT_PUBLIC_COPILOT_FAKE=1`) and the guide scene opens `/chat?guide=fake`; the Account 360
  brief is real (generated once with the key in `.env.local`, then cached).
- The web is built from an rsync'd copy under `build/video/webcopy` so another `next build` in
  `apps/web` can't replace the chunks a running recording serves.
- Needs a green tree: `pnpm build` must pass.
