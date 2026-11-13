import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw

from .audio import collect_media_assets, download_file
from .video import synthesize_voice

OUTPUT_DIR = Path(os.getenv("ATLAS_MEDIA_OUTPUT_DIR", "./output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _local_placeholder(prompt: str, output_path: Path) -> str:
    """Create a deterministic local visual when no source image is available."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1280, 720
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        blend = y / max(height - 1, 1)
        for x in range(width):
            pixels[x, y] = (
                int(18 + 30 * blend),
                int(32 + 42 * blend),
                int(58 + 65 * blend),
            )
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((70, 70, width - 70, height - 70), radius=28, outline=(190, 205, 225), width=3)
    draw.text((110, 120), "ATLASONEPRO", fill=(235, 240, 248))
    words = prompt.strip().split()
    lines, line = [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if len(candidate) > 55:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    for index, text in enumerate(lines[:7]):
        draw.text((110, 230 + index * 48), text, fill=(255, 255, 255))
    image.save(output_path, format="PNG")
    return str(output_path)


def generate_image_from_prompt(prompt: str, output_path: Optional[str] = None) -> str:
    if not prompt or not prompt.strip():
        raise ValueError("Prompt is required")
    target = Path(output_path) if output_path else OUTPUT_DIR / f"atlas-image-{uuid.uuid4().hex[:10]}.png"
    target.parent.mkdir(parents=True, exist_ok=True)

    # Try a public image source first; always retain a local fallback.
    try:
        assets = collect_media_assets(prompt.strip(), image_limit=1, video_limit=0)
        images = assets.get("images", [])
        if images:
            url = images[0].get("image_url") or images[0].get("thumb_url")
            if url:
                return download_file(url, str(target))
    except Exception:
        pass
    return _local_placeholder(prompt.strip(), target)


def create_video_from_images(
    image_paths: List[str],
    output_path: str,
    duration_per_image: float = 3.0,
    audio_path: Optional[str] = None,
) -> str:
    if not image_paths:
        raise ValueError("No images supplied for video generation")
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg is required to create video output")
    final_path = Path(output_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = OUTPUT_DIR / f"concat-{uuid.uuid4().hex[:10]}.txt"
    clip_paths = []
    try:
        for idx, image in enumerate(image_paths):
            clip = OUTPUT_DIR / f"clip-{uuid.uuid4().hex[:10]}-{idx}.mp4"
            command = [
                "ffmpeg", "-y", "-loop", "1", "-i", str(image),
                "-t", str(duration_per_image),
                "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
                "-pix_fmt", "yuv420p", "-c:v", "libx264", str(clip),
            ]
            subprocess.run(command, check=True, capture_output=True)
            clip_paths.append(clip)
        with concat_file.open("w", encoding="utf-8") as handle:
            for clip in clip_paths:
                handle.write(f"file '{clip.as_posix()}'\n")
        command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file)]
        if audio_path and Path(audio_path).exists():
            command += ["-i", str(audio_path), "-shortest"]
        command += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if audio_path and Path(audio_path).exists():
            command += ["-c:a", "aac"]
        command += [str(final_path)]
        subprocess.run(command, check=True, capture_output=True)
        return str(final_path)
    finally:
        concat_file.unlink(missing_ok=True)
        for clip in clip_paths:
            clip.unlink(missing_ok=True)


def generate_video_from_prompt(
    prompt: str,
    output_path: Optional[str] = None,
    narration: Optional[str] = None,
) -> str:
    if not prompt or not prompt.strip():
        raise ValueError("Prompt is required")
    image_path = generate_image_from_prompt(prompt)
    audio_path = None
    if narration and narration.strip():
        audio_path = str(OUTPUT_DIR / f"atlas-voice-{uuid.uuid4().hex[:10]}.mp3")
        synthesize_voice(narration.strip(), audio_path)
    target = output_path or str(OUTPUT_DIR / f"atlas-video-{uuid.uuid4().hex[:10]}.mp4")
    return create_video_from_images([image_path], target, audio_path=audio_path)
