"""FastAPI application to convert VOB files from OneDrive to MP4 and upload them back."""
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aiohttp
import aiofiles
import asyncio
import logging
import os
import re
import json
import uuid
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from tqdm.asyncio import tqdm as tqdm_asyncio

# --- Constants ---
OUTPUT_DIR = "vob_files"
MP4_OUTPUT_DIR = "mp4_files"
LOG_DIR = "logs"
CONCURRENT = {"downloads": 3, "uploads": 3, "conversions": 2}
CHUNK_SIZE = 62_914_560  # 60 MB
RETRIES_PER_CHUNK = 5

AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_API = "https://graph.microsoft.com/v1.0/me/drive"
SCOPE = "https://graph.microsoft.com/.default openid profile offline_access"

FFMPEG_BASE = ["ffmpeg", "-y", "-fflags", "+genpts"]
FFMPEG_ENCODE = [
    "-c:v", "h264_nvenc", "-preset", "p2", "-b:v", "5M",
    "-vf", "scale=1280:720", "-r", "30",
    "-c:a", "aac", "-b:a", "128k",
    "-progress", "pipe:2",
]
FFPROBE_BASE = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=nb_frames", "-of", "json"]

# --- Setup ---
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MP4_OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(LOG_DIR, "app.log"))]
)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models and State ---
class ConvertRequest(BaseModel):
    """Request model for file conversion."""
    refresh_token: str
    onedrive_url: str

progress_state = {}  # Task ID -> Progress (0-100)

# --- Utility Functions ---
async def refresh_access_token(refresh_token: str) -> dict:
    """Refresh OneDrive access token."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "scope": SCOPE,
            }
        ) as response:
            data = await response.json()
            if response.status != 200:
                raise HTTPException(status_code=response.status, detail="Failed to refresh token")
            return data

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

# --- Core Functions ---
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

async def convert_vob_to_mp4(file_path: str, position: int = 0) -> str | None:
    """Convert VOB to MP4 with progress bar, handling missing duration."""
    async with semaphore_conversion:
        output_file = os.path.join(MP4_OUTPUT_DIR, os.path.basename(file_path).replace(".VOB", ".mp4"))
        log_file = os.path.join(LOG_DIR, f"{os.path.basename(file_path)}.log")
        command = build_ffmpeg_command(file_path, output_file)

        try:
            # Get duration and setup progress bar
            total_duration, total_frames = await get_video_duration(file_path)
            use_frames = total_duration is None or total_duration <= 0
            total = total_frames if use_frames else total_duration
            unit = "frames" if use_frames else "s"
            desc = f"Converting {os.path.basename(file_path)}"

            bar_args = {
                "desc": desc,
                "position": position,
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

                time_pattern = r"time=(\d{2}:\d{2}:\d{2}\.\d{2})"
                frame_pattern = r"frame=(\d+)"
                last_progress = 0

                async with aiofiles.open(log_file, "w", encoding="utf-8") as f:
                    while process.returncode is None:
                        try:
                            line = await asyncio.wait_for(process.stderr.readline(), timeout=5.0)
                            if not line:
                                break
                            line = line.decode().strip()
                            if line:
                                await f.write(f"{line}\n")
                                frame_match = re.search(frame_pattern, line)
                                if frame_match:
                                    current_frames = int(frame_match.group(1))
                                    if total is None:
                                        progress_bar.update(1)
                                        progress_bar.set_postfix(frames=current_frames)
                                    elif use_frames and total_frames:
                                        progress_bar.update(current_frames - last_progress)
                                        last_progress = current_frames
                                        progress_bar.set_postfix(frames=current_frames)
                                elif total_duration:
                                    time_match = re.search(time_pattern, line)
                                    if time_match:
                                        h, m, s = map(float, time_match.group(1).split(':'))
                                        current_time = h * 3600 + m * 60 + s
                                        progress_bar.update(current_time - last_progress)
                                        last_progress = current_time
                                        progress_bar.set_postfix(time=time_match.group(1))
                        except asyncio.TimeoutError:
                            logger.warning(f"Timeout reading FFmpeg stderr for {file_path}")
                            continue
                        except Exception as e:
                            logger.error(f"Error reading FFmpeg stderr for {file_path}: {e}")
                            break

                await process.wait()

                if process.returncode != 0:
                    async with aiofiles.open(log_file, "r", encoding="utf-8") as f:
                        error_msg = await f.read()
                    logger.error(f"FFmpeg failed for {file_path}: See {log_file}")
                    raise Exception(f"FFmpeg conversion failed: {error_msg}")

                logger.info(f"Converted {file_path} to {output_file}")
                return output_file
        except Exception as e:
            logger.error(f"Error converting {file_path}: {e}")
            raise

async def download_file(http_client: aiohttp.ClientSession, item_id: str, item_name: str, item_parent_id: str, refresh_token: str) -> str:
    """Download VOB file from OneDrive."""
    async with semaphore_download:
        try:
            token = await refresh_access_token(refresh_token)
            async with http_client.get(
                f"{GRAPH_API}/items/{item_id}/content",
                headers={"Authorization": f"Bearer {token['access_token']}"}
            ) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                file_path = os.path.join(OUTPUT_DIR, f"{item_parent_id}-{item_name}")

                with tqdm_asyncio(
                    total=total_size, unit="B", unit_scale=True, unit_divisor=1024,
                    desc=f"Downloading {item_name}"
                ) as progress_bar:
                    async with aiofiles.open(file_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                            if chunk:
                                await f.write(chunk)
                                progress_bar.update(len(chunk))

                logger.info(f"Downloaded {item_name}")
                return file_path
        except aiohttp.ClientError as e:
            logger.error(f"Error downloading {item_name}: {e}")
            raise HTTPException(status_code=500, detail=f"Error downloading {item_name}: {e}")

async def upload_file(file_path: str, refresh_token: str, position: int = 0) -> str:
    """Upload MP4 file to OneDrive."""
    async with semaphore_upload:
        try:
            token = await refresh_access_token(refresh_token)
            base_name = os.path.basename(file_path)
            parent_id, filename = base_name.split("-", 1) if "-" in base_name else (None, base_name)
            if not parent_id:
                raise ValueError("Invalid file name format: missing parent ID")

            total_size = os.path.getsize(file_path)
            if total_size == 0:
                logger.warning(f"Empty file: {file_path}")

            async with aiohttp.ClientSession() as http_client:
                async with http_client.post(
                    f"{GRAPH_API}/items/{parent_id}:/{filename}:/createUploadSession",
                    headers={"Authorization": f"Bearer {token['access_token']}", "Content-Type": "application/json"},
                    json={"item": {"@microsoft.graph.conflictBehavior": "replace"}}
                ) as response:
                    response.raise_for_status()
                    upload_url = (await response.json()).get("uploadUrl")
                    if not upload_url:
                        raise ValueError("No upload URL received")

                chunk_number = (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE
                async with aiofiles.open(file_path, "rb") as f:
                    with tqdm_asyncio(
                        total=chunk_number, unit="chunk", desc=f"Uploading {filename}",
                        position=position, mininterval=0.1, smoothing=0.05, leave=True
                    ) as progress_bar:
                        for i in range(chunk_number):
                            chunk = await f.read(CHUNK_SIZE)
                            start = i * CHUNK_SIZE
                            end = start + len(chunk) - 1
                            headers = {
                                "Content-Length": str(len(chunk)),
                                "Content-Range": f"bytes {start}-{end}/{total_size}"
                            }
                            for attempt in range(1, RETRIES_PER_CHUNK + 1):
                                try:
                                    async with http_client.put(upload_url, headers=headers, data=chunk) as response:
                                        if response.status in (200, 201, 202):
                                            break
                                        logger.warning(f"Chunk {i+1}/{chunk_number} failed, attempt {attempt}")
                                        if attempt == RETRIES_PER_CHUNK:
                                            raise Exception("Chunk upload failed")
                                except aiohttp.ClientError as e:
                                    if attempt == RETRIES_PER_CHUNK:
                                        raise e
                                    await asyncio.sleep(2 ** (attempt - 1))
                            progress_bar.update(1)

            logger.info(f"Uploaded {filename}")
            return filename
        except Exception as e:
            logger.error(f"Error uploading {file_path}: {e}")
            raise HTTPException(status_code=500, detail=f"File upload failed: {e}")

async def find_vob_files(http_client: aiohttp.ClientSession, item_ids: list[str], refresh_token: str) -> list[tuple]:
    """Find VOB files in OneDrive folder."""
    final_items = []
    pending_ids = item_ids[:]
    token = await refresh_access_token(refresh_token)

    while pending_ids:
        new_ids = []
        for item_id in pending_ids:
            async with http_client.get(
                f"{GRAPH_API}/items/{item_id}/children",
                headers={"Authorization": f"Bearer {token['access_token']}"}
            ) as response:
                response.raise_for_status()
                items = (await response.json())["value"]
                for item in items:
                    if item["name"].endswith(".VOB"):
                        final_items.append((item["id"], item["name"], item["parentReference"]["id"]))
                    elif "file" not in item:
                        new_ids.append(item["id"])
        pending_ids = new_ids

    logger.info(f"Found {len(final_items)} VOB files")
    return final_items

async def process_files(item_ids: list[str], refresh_token: str, task_id: str) -> None:
    """Process VOB files: download, convert, upload."""
    progress_state[task_id] = 0
    async with aiohttp.ClientSession() as http_client:
        # Download
        final_items = await find_vob_files(http_client, item_ids, refresh_token)
        download_tasks = [
            download_file(http_client, item_id, name, parent_id, refresh_token)
            for item_id, name, parent_id in final_items
        ]
        downloaded_files = await tqdm_asyncio.gather(
            *download_tasks, desc="Downloading files", position=len(final_items)
        )
        progress_state[task_id] = 50

        # Convert
        conversion_tasks = [convert_vob_to_mp4(file, i) for i, file in enumerate(downloaded_files)]
        converted_files = []
        with tqdm_asyncio(
            total=len(conversion_tasks), desc="Converting files", position=len(downloaded_files), unit="file"
        ) as pbar:
            results = await asyncio.gather(*conversion_tasks, return_exceptions=True)
            for file, result in zip(downloaded_files, results):
                if isinstance(result, Exception):
                    logger.error(f"Conversion failed for {file}: {result}")
                elif result:
                    converted_files.append(result)
                pbar.update(1)
        progress_state[task_id] = 75
        await asyncio.sleep(0.1)

        # Upload
        upload_tasks = [upload_file(file, refresh_token, i) for i, file in enumerate(converted_files)]
        await tqdm_asyncio.gather(
            *upload_tasks, desc="Uploading files", position=len(downloaded_files)
        )
        progress_state[task_id] = 100

# --- Semaphores ---
semaphore_download = asyncio.Semaphore(CONCURRENT["downloads"])
semaphore_upload = asyncio.Semaphore(CONCURRENT["uploads"])
semaphore_conversion = asyncio.Semaphore(CONCURRENT["conversions"])

# --- API Routes ---
@app.post("/convert")
async def convert_files(request: ConvertRequest):
    """Start conversion process for VOB files."""
    try:
        task_id = str(uuid.uuid4())
        progress_state[task_id] = 0

        parsed_url = urlparse(request.onedrive_url)
        item_id = parse_qs(parsed_url.query).get("id", [None])[0]
        if not item_id:
            raise ValueError("No item_id found in URL")
        logger.info(f"Extracted item_id: {item_id}")

        await process_files([item_id], request.refresh_token, task_id)
        return JSONResponse(content={"message": "Files processed successfully", "task_id": task_id})
    except Exception as e:
        logger.error(f"Error processing files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/progress/{task_id}")
async def get_progress(task_id: str):
    """Get progress for a task."""
    if task_id in progress_state:
        return JSONResponse(content={"task_id": task_id, "progress": progress_state[task_id]})
    raise HTTPException(status_code=404, detail="Task ID not found")