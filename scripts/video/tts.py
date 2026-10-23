"""Per-scene voiceover for the demo video (OpenAI TTS, gpt-4o-mini-tts).

    uv run python scripts/video/tts.py   # needs OPENAI_API_KEY; writes build/video/audio/*.mp3

Regenerates a clip only when its narration text changed (the text is kept next to the .mp3),
so re-runs cost nothing and edited lines are picked up automatically.
"""

import json
import os
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
SCENES = json.loads((ROOT / "scripts/video/narration.json").read_text())
TEASER = json.loads((ROOT / "scripts/video/teaser.json").read_text())
OUT = ROOT / "build/video/audio"
VOICE = os.environ.get("IGS_VIDEO_VOICE", "ash")
INSTRUCTIONS = (
    "Calm, confident, professional product-demo narrator. Neutral American English, "
    "moderate pace, clear pauses at sentence ends. No hype."
)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    client = OpenAI()
    for scene in [*SCENES, {"id": "teaser", "text": TEASER["text"]}]:
        target = OUT / f"{scene['id']}.mp3"
        stamp = target.with_suffix(".txt")
        if target.exists() and stamp.exists() and stamp.read_text() == scene["text"]:
            continue
        with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=VOICE,
            input=scene["text"],
            instructions=INSTRUCTIONS,
            response_format="mp3",
        ) as response:
            response.stream_to_file(target)
        stamp.write_text(scene["text"])
        print("wrote", target.relative_to(ROOT))


if __name__ == "__main__":
    main()
