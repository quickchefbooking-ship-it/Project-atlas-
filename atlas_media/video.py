import os
from typing import Optional

from gtts import gTTS

OUTPUT_DIR = os.getenv("ATLAS_MEDIA_OUTPUT_DIR", "./output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def synthesize_voice(text: str, output_path: str, lang: str = "en") -> str:
    if not text or not text.strip():
        raise ValueError("Speech text is empty")
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(output_path)
    return output_path
