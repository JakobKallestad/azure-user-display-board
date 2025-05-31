"""Video processing functions for conversion and metadata extraction."""
import os
import re
import json
import asyncio
import logging
import aiofiles
from tqdm.asyncio import tqdm as tqdm_asyncio
from config import FFMPEG_BASE, FFMPEG_ENCODE, FFPROBE_BASE, MP4_OUTPUT_DIR, LOG_DIR
from progress import update_file_progress

logger = logging.getLogger(__name__)

def build_ffmpeg_command(input_file: str, output_file: str) -> list:
    """Build FFmpeg command for VOB to MP4 conversion."""
    return FFMPEG_BASE + ["-i", input_file] + FFMPEG_ENCODE + [output_file]

async def parse_ffmpeg_duration(stderr_text: str) -> float | None:
    """Parse duration from FFmpeg stderr output."""
    match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", stderr_text)
    if match:
        h, m, s = map(float, match.groups())
        return h * 3600 + m * 60 + s
    return None

async def get_video_duration(file_path: str) -> tuple[float | None, int | None]:
    """Extract video duration and frame count using ffprobe or FFmpeg fallback."""
    # Try ffprobe
    try:
        process = await asyncio.create_subprocess_exec(
            *FFPROBE_BASE, file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            data = json.loads(stdout.decode())
            duration = float(data.get("format", {}).get("duration", 0)) or None
            frames = int(data.get("streams", [{}])[0].get("nb_frames", 0)) or None
            if duration:
                logger.info(f"Duration for {file_path}: {duration} seconds")
                return duration, frames
    except Exception as e:
        logger.warning(f"ffprobe failed for {file_path}: {e}")

    # Fallback to FFmpeg
    try:
        process = await asyncio.create_subprocess_exec(
            *FFMPEG_BASE, "-i", file_path, "-f", "null", "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        duration = await parse_ffmpeg_duration(stderr.decode())
        if duration:
            logger.info(f"Fallback duration for {file_path}: {duration} seconds")
            return duration, None
    except Exception as e:
        logger.warning(f"FFmpeg duration extraction failed for {file_path}: {e}")

    logger.warning(f"No duration or frames detected for {file_path}")
    return None, None

async def convert_vob_to_mp4(vob_path: str, semaphore_conversion, task_id: str = None, file_index: int = 0, total_files: int = 0, conversion_index: int = 0, session_id: str = None) -> str:
    """Convert VOB file to MP4 format with progress tracking."""
    async with semaphore_conversion:
        try:
            # Use session_id in path if provided
            if session_id:
                mp4_session_dir = os.path.join(MP4_OUTPUT_DIR, session_id)
                os.makedirs(mp4_session_dir, exist_ok=True)  # Create directory if it doesn't exist
                mp4_filename = os.path.splitext(os.path.basename(vob_path))[0] + ".mp4"
                mp4_path = os.path.join(mp4_session_dir, mp4_filename)
            else:
                mp4_filename = os.path.splitext(os.path.basename(vob_path))[0] + ".mp4"
                mp4_path = os.path.join(MP4_OUTPUT_DIR, mp4_filename)
            
            log_file = os.path.join(LOG_DIR, f"{os.path.basename(vob_path)}.log")
            command = build_ffmpeg_command(vob_path, mp4_path)
            
            filename = os.path.basename(vob_path)
            
            if task_id:
                update_file_progress(task_id, filename, "convert", 0)

            # Get duration and setup progress bar
            total_duration, total_frames = await get_video_duration(vob_path)
            use_frames = total_duration is None or total_duration <= 0
            total = total_frames if use_frames else total_duration
            unit = "frames" if use_frames else "s"
            desc = f"Converting {filename}"

            bar_args = {
                "desc": desc,
                "position": conversion_index,
                "mininterval": 0.1,
                "smoothing": 0.05,
                "leave": True,
                "unit": "frame" if total is None else unit
            }
            if total is not None:
                bar_args["total"] = total

            with tqdm_asyncio(**bar_args) as progress_bar:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=10 * 1024 * 1024
                )

                last_progress = 0
                async with aiofiles.open(log_file, "w", encoding="utf-8") as log_f:
                    while True:
                        try:
                            line = await asyncio.wait_for(process.stderr.readline(), timeout=5.0)
                            if not line:
                                break
                            line = line.decode("utf-8", errors="ignore").strip()
                            await log_f.write(line + "\n")

                            if use_frames:
                                frame_match = re.search(r"frame=\s*(\d+)", line)
                                if frame_match and total_frames:
                                    current_frame = int(frame_match.group(1))
                                    progress_bar.update(current_frame - last_progress)
                                    last_progress = current_frame
                                    progress_bar.set_postfix(frame=current_frame)
                                    if task_id:
                                        frame_progress = int((current_frame / total_frames) * 100)
                                        update_file_progress(task_id, filename, "convert", frame_progress)
                            else:
                                time_pattern = r"time=(\d{2}:\d{2}:\d{2}\.\d{2})"
                                if total_duration and total_duration > 0:
                                    time_match = re.search(time_pattern, line)
                                    if time_match:
                                        h, m, s = map(float, time_match.group(1).split(':'))
                                        current_time = h * 3600 + m * 60 + s
                                        progress_bar.update(current_time - last_progress)
                                        last_progress = current_time
                                        progress_bar.set_postfix(time=time_match.group(1))
                                        if task_id:
                                            time_progress = int((current_time / total_duration) * 100)
                                            update_file_progress(task_id, filename, "convert", time_progress)
                        except asyncio.TimeoutError:
                            logger.warning(f"Timeout reading FFmpeg stderr for {vob_path}")
                            continue
                        except Exception as e:
                            logger.error(f"Error reading FFmpeg stderr for {vob_path}: {e}")
                            break

                await process.wait()

                if process.returncode != 0:
                    async with aiofiles.open(log_file, "r", encoding="utf-8") as f:
                        error_msg = await f.read()
                    logger.error(f"FFmpeg failed for {vob_path}: See {log_file}")
                    if task_id:
                        from progress import progress_state
                        progress_state[task_id]["failed_files"].append(f"Conversion failed: {filename}")
                    raise Exception(f"FFmpeg conversion failed: {error_msg}")

                logger.info(f"Converted {vob_path} to {mp4_path}")
                
                if task_id:
                    update_file_progress(task_id, filename, "convert", 100, completed=True)
                
                return mp4_path
        except Exception as e:
            logger.error(f"Error converting {vob_path}: {e}")
            if task_id:
                from progress import progress_state
                progress_state[task_id]["failed_files"].append(f"Conversion error: {filename}") 