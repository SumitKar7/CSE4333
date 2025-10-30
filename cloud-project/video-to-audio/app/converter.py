# app/converter.py
"""
Simple FFmpeg-based video -> audio converter.
Provides convert_to_audio(input_path, output_path, codec='mp3', quality=2)
"""

import shutil
import subprocess
from pathlib import Path
from typing import Tuple

class ConversionError(RuntimeError):
    pass

def _ffmpeg_exists() -> bool:
    """Return True if ffmpeg binary is available on PATH."""
    return shutil.which("ffmpeg") is not None

def convert_to_audio(input_path: str, output_path: str, codec: str = "mp3", quality: int = 2) -> Tuple[int, str]:
    """
    Convert input video file to an audio file.

    Args:
      input_path: path to input video
      output_path: path to output audio (extension should match codec, e.g., .mp3)
      codec: 'mp3' or 'aac' or 'copy' (copy will copy audio stream if compatible)
      quality: for mp3 - qscale (0 best, 9 worst). We'll map to ffmpeg args.

    Returns:
      (return_code, output_path)

    Raises:
      ConversionError on obvious problems.
    """
    input_path = str(input_path)
    output_path = str(output_path)

    # Basic checks
    if not _ffmpeg_exists():
        raise ConversionError("ffmpeg not found on PATH. Install ffmpeg and retry.")

    inp = Path(input_path)
    if not inp.exists() or not inp.is_file():
        raise ConversionError(f"Input file not found: {input_path}")

    out = Path(output_path)
    out_parent = out.parent
    out_parent.mkdir(parents=True, exist_ok=True)

    # Build ffmpeg command
    if codec == "mp3":
        # -vn: no video, -q:a: variable bitrate quality for libmp3lame (0..9)
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vn", "-acodec", "libmp3lame",
            "-q:a", str(int(quality)),
            output_path
        ]
    elif codec == "aac":
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vn", "-c:a", "aac",
            "-b:a", "128k",
            output_path
        ]
    elif codec == "copy":
        # copy the audio stream (container must support the audio format)
        cmd = ["ffmpeg", "-y", "-i", input_path, "-vn", "-c:a", "copy", output_path]
    else:
        raise ConversionError(f"Unsupported codec: {codec}")

    proc = subprocess.run(cmd, capture_output=True)

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="ignore")
        raise ConversionError(f"ffmpeg failed (code {proc.returncode}): {stderr}")

    return proc.returncode, output_path
