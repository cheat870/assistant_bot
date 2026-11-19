import os
import re
import uuid
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def get_ffmpeg_binary() -> str:
    """Find installed ffmpeg binary or fallback to imageio_ffmpeg."""
    which_path = shutil.which("ffmpeg")
    if which_path:
        return which_path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

def parse_time_to_seconds(time_str: str) -> Optional[float]:
    """Parse time string like '10', '00:15', '01:30', '00:01:45' into seconds."""
    if not time_str:
        return None
    time_str = time_str.strip().replace("s", "").replace("m", ":")
    parts = time_str.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None
    return None

def trim_video(input_path: str, start_time: str, end_time: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Trim a video file between start_time and end_time.
    Returns (output_path, error_message).
    """
    start_sec = parse_time_to_seconds(start_time)
    end_sec = parse_time_to_seconds(end_time)

    if start_sec is None or end_sec is None:
        return None, "ទម្រង់ម៉ោងមិនត្រឹមត្រូវឡើយ (ឧ. 00:10 00:45 ឬ 10 45)"
    if start_sec >= end_sec:
        return None, "ម៉ោងចាប់ផ្ដើមត្រូវតែតូចជាងម៉ោងបញ្ចប់"

    duration = end_sec - start_sec
    if duration > 300: # Max 5 minutes per trim to prevent abuse
        return None, "រយៈពេលកាត់អតិបរមាគឺត្រឹម ៥ នាទី"

    ffmpeg_bin = get_ffmpeg_binary()
    in_file = Path(input_path)
    if not in_file.exists():
        return None, "រកមិនឃើញ File វីដេអូដើមឡើយ"

    unique_id = uuid.uuid4().hex[:8]
    output_path = in_file.parent / f"trimmed_{unique_id}_{in_file.name}"

    # Use fast seeking before -i and re-encode for frame-perfect cut
    cmd = [
        ffmpeg_bin,
        "-y",
        "-ss", str(start_sec),
        "-i", str(in_file),
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path)
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            return str(output_path), None
        else:
            err = res.stderr.decode("utf-8", errors="ignore")[-200:]
            logger.error(f"FFmpeg trim error: {err}")
            return None, f"កំហុសបច្ចេកទេសកាត់វីដេអូ៖ {err[:80]}"
    except subprocess.TimeoutExpired:
        return None, "ការកាត់វីដេអូចំណាយពេលយូរពេក (Timeout)"
    except Exception as e:
        logger.error(f"Trim exception: {e}")
        return None, f"កំហុសក្នុងការកាត់វីដេអូ៖ {str(e)[:100]}"

def convert_video_to_gif(input_path: str, max_duration: int = 15) -> Tuple[Optional[str], Optional[str]]:
    """
    Convert video to a smooth, looping Telegram-compatible animated GIF (.mp4 with muted audio).
    Returns (output_path, error_message).
    """
    ffmpeg_bin = get_ffmpeg_binary()
    in_file = Path(input_path)
    if not in_file.exists():
        return None, "រកមិនឃើញ File វីដេអូដើមឡើយ"

    unique_id = uuid.uuid4().hex[:8]
    output_path = in_file.parent / f"gif_{unique_id}.mp4"

    # Scale width to 480px, mute audio, limit fps to 20 for optimal Telegram Animation
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(in_file),
        "-t", str(max_duration),
        "-an", # No audio
        "-vf", "scale=480:-2:flags=lanczos,fps=20",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "faster",
        "-crf", "24",
        "-movflags", "+faststart",
        str(output_path)
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
        if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            return str(output_path), None
        else:
            err = res.stderr.decode("utf-8", errors="ignore")[-200:]
            logger.error(f"FFmpeg gif error: {err}")
            return None, f"កំហុសក្នុងការបម្លែងជា GIF៖ {err[:80]}"
    except subprocess.TimeoutExpired:
        return None, "ការបម្លែង GIF ចំណាយពេលយូរពេក (Timeout)"
    except Exception as e:
        logger.error(f"Convert GIF exception: {e}")
        return None, f"កំហុសក្នុងការបម្លែង GIF៖ {str(e)[:100]}"
