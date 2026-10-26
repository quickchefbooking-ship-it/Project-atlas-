import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

OUTPUT_DIR = os.getenv("ATLAS_MEDIA_OUTPUT_DIR", "./output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def create_video_from_images(image_paths: List[str], output_path: str, duration_per_image: float = 3.0, audio_path: Optional[str] = None) -> str:
    if not image_paths:
        raise ValueError("No images supplied for video generation")
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg is required to create video output. Install ffmpeg on the system.")

    temp_dir = Path(OUTPUT_DIR) / "tmp_video"
    temp_dir.mkdir(parents=True, exist_ok=True)
    concat_file = temp_dir / "concat.txt"
    clip_paths = []

    for idx, image in enumerate(image_paths):
        clip = temp_dir / f"clip_{idx}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(image),
            "-t", str(duration_per_image),
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            str(clip),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        clip_paths.append(str(clip))

    with open(concat_file, "w", encoding="utf-8") as fh:
        for clip in clip_paths:
            fh.write(f"file '{clip}'\n")

    final_path = output_path
    if audio_path and os.path.exists(audio_path):
        temp_output = str(Path(OUTPUT_DIR) / "tmp_video_output.mp4")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:v", "libx264", "-pix_fmt", "yuv420p", temp_output], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-i", temp_output, "-i", audio_path, "-shortest", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", final_path], check=True, capture_output=True)
        if os.path.exists(temp_output):
            os.remove(temp_output)
    else:
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:v", "libx264", "-pix_fmt", "yuv420p", final_path], check=True, capture_output=True)

    return final_path
