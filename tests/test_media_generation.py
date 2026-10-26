import hashlib
import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from .audio import synthesize_voice
from .sources import collect_media_assets, download_file
from .video import create_video_from_images

OUTPUT_DIR = os.getenv("ATLAS_MEDIA_OUTPUT_DIR", "./output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _local_visual(prompt: str, output_path: str) -> str:
    width, height = 1280, 720
    image = Image.new("RGB", (width, height), color=(20, 40, 60))
    draw = ImageDraw.Draw(image)
    for x in range(0, width, 30):
        for y in range(0, height, 30):
            shade = (x // 30 + y // 30) % 200
            draw.rectangle((x, y, x + 24, y + 24), fill=(20 + shade, 35 + ((x + y) % 80), 60 + ((x * 2 + y) % 85)))
    title = prompt[:80]
    draw.text((60, 60), title, fill=(255, 255, 255))
    draw.text((60, 660), "Atlas Media Generator", fill=(214, 228, 255))
    image.save(output_path)
    return output_path


def generate_image_from_prompt(prompt: str, output_path: Optional[str] = None) -> str:
    if not prompt.strip():
        raise ValueError("Prompt is required")
    if output_path is None:
        slug = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:12]
        output_path = str(Path(OUTPUT_DIR) / f"{slug}.png")

    assets = collect_media_assets(prompt, image_limit=2, video_limit=0)
    for item in assets.get("images", []):
        url = item.get("image_url") or item.get("thumb_url")
        if not url:
            continue
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            download_file(url, str(path))
            return str(path)
        except Exception:
            continue

    return _local_visual(prompt, output_path)


def generate_video_from_prompt(prompt: str, output_path: Optional[str] = None, narration: Optional[str] = None) -> str:
    if not prompt.strip():
        raise ValueError("Prompt is required")
    if output_path is None:
        slug = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:12]
        output_path = str(Path(OUTPUT_DIR) / f"{slug}.mp4")

    assets = collect_media_assets(prompt, image_limit=4, video_limit=2)
    image_paths = []
    for item in assets.get("images", []):
        url = item.get("image_url") or item.get("thumb_url")
        if not url:
            continue
        tmp = str(Path(OUTPUT_DIR) / f"tmp_{hashlib.md5(url.encode()).hexdigest()[:10]}.jpg")
        try:
            download_file(url, tmp)
            image_paths.append(tmp)
        except Exception:
            continue

    if not image_paths:
        image_path = str(Path(OUTPUT_DIR) / f"{hashlib.md5(prompt.encode()).hexdigest()[:12]}.png")
        generate_image_from_prompt(prompt, image_path)
        image_paths = [image_path]

    narration_path = None
    if narration and narration.strip():
        narration_path = str(Path(OUTPUT_DIR) / f"{hashlib.md5((prompt + narration).encode()).hexdigest()[:12]}.mp3")
        try:
            synthesize_voice(narration, narration_path, lang="en")
        except Exception:
            narration_path = None

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    create_video_from_images(image_paths[:3], output_path, duration_per_image=3.0, audio_path=narration_path)
    return output_path
