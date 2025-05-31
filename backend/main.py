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
import time
from datetime import datetime, timedelta

# --- Constants ---
OUTPUT_DIR = "vob_files"
MP4_OUTPUT_DIR = "mp4_files"
LOG_DIR = "logs"
CONCURRENT = {"downloads": 3, "uploads": 3, "conversions": 3}
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
    file_ids: list[str]  # Changed from onedrive_url to list of file IDs

class ProgressInfo(BaseModel):
    """Progress information model."""
    task_id: str
    overall_progress: int
    current_phase: str
    phase_progress: int
    current_file: str = ""
    files_completed: int = 0
    total_files: int = 0
    details: str = ""
    estimated_time_remaining: str = ""

# Enhanced progress state to store detailed information
progress_state = {}  # Task ID -> ProgressInfo dict

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

async def convert_vob_to_mp4(file_path: str, task_id: str = None, file_index: int = 0, total_files: int = 0, position: int = 0) -> str | None:
    """Convert VOB to MP4 with enhanced parallel progress tracking."""
    async with semaphore_conversion:
        output_file = os.path.join(MP4_OUTPUT_DIR, os.path.basename(file_path).replace(".VOB", ".mp4"))
        log_file = os.path.join(LOG_DIR, f"{os.path.basename(file_path)}.log")
        command = build_ffmpeg_command(file_path, output_file)
        
        filename = os.path.basename(file_path)
        
        if task_id:
            update_file_progress(task_id, filename, "convert", 0)

        try:
            # Get duration and setup progress bar
            total_duration, total_frames = await get_video_duration(file_path)
            use_frames = total_duration is None or total_duration <= 0
            total = total_frames if use_frames else total_duration
            unit = "frames" if use_frames else "s"
            desc = f"Converting {filename}"

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
                    if task_id:
                        progress_state[task_id]["failed_files"].append(f"Conversion failed: {filename}")
                    raise Exception(f"FFmpeg conversion failed: {error_msg}")

                logger.info(f"Converted {file_path} to {output_file}")
                
                if task_id:
                    update_file_progress(task_id, filename, "convert", 100, completed=True)
                
                return output_file
        except Exception as e:
            logger.error(f"Error converting {file_path}: {e}")
            if task_id:
                progress_state[task_id]["failed_files"].append(f"Conversion error: {filename}")


async def upload_file(file_path: str, refresh_token: str, task_id: str = None, file_index: int = 0, total_files: int = 0, position: int = 0) -> str:
    """Upload MP4 file to OneDrive with enhanced parallel progress tracking."""
    async with semaphore_upload:
        try:
            base_name = os.path.basename(file_path)
            parent_id, filename = base_name.split("-", 1) if "-" in base_name else (None, base_name)
            if not parent_id:
                raise ValueError("Invalid file name format: missing parent ID")

            if task_id:
                update_file_progress(task_id, file_path, "upload", 0)

            token = await refresh_access_token(refresh_token)
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
                uploaded_chunks = 0

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
                            
                            uploaded_chunks += 1
                            progress_bar.update(1)
                            
                            if task_id:
                                chunk_progress = int((uploaded_chunks / chunk_number) * 100)
                                update_file_progress(task_id, file_path, "upload", chunk_progress)

            logger.info(f"Uploaded {filename}")
            
            if task_id:
                update_file_progress(task_id, file_path, "upload", 100, completed=True)
            
            return filename
        except Exception as e:
            logger.error(f"Error uploading {file_path}: {e}")
            if task_id:
                progress_state[task_id]["failed_files"].append(f"Upload failed: {os.path.basename(file_path)}")
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

async def process_selected_files(file_ids: list[str], refresh_token: str, task_id: str) -> None:
    """Process selected VOB files: download, convert, upload with enhanced parallel progress tracking."""
    total_files = len(file_ids)
    
    update_progress(task_id, 
                   overall_progress=5,
                   current_phase="downloading",
                   details=f"Starting parallel downloads for {total_files} selected files...")
    
    async with aiohttp.ClientSession() as http_client:
        # Get file names for each selected file
        file_info_tasks = []
        for file_id in file_ids:
            file_info_tasks.append(get_file_info(http_client, file_id, refresh_token))
        
        file_infos = await asyncio.gather(*file_info_tasks, return_exceptions=True)
        valid_file_infos = [(file_id, info) for file_id, info in zip(file_ids, file_infos) 
                           if not isinstance(info, Exception)]
        
        # Download files in parallel - now download_file_by_id will handle parent ID internally
        download_tasks = [
            download_file_by_id(http_client, file_id, info['name'], refresh_token, task_id, i, total_files)
            for i, (file_id, info) in enumerate(valid_file_infos)
        ]
        downloaded_files = await asyncio.gather(*download_tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_downloads = [f for f in downloaded_files if not isinstance(f, Exception)]
        
        # Update for conversion phase
        update_progress(task_id,
                       overall_progress=35,
                       current_phase="converting",
                       files_completed=0,  # Reset for this phase
                       details=f"Downloaded {len(valid_downloads)} files. Starting parallel conversions...")

        # Convert files in parallel
        conversion_tasks = [
            convert_vob_to_mp4(file, task_id, i, len(valid_downloads), i) 
            for i, file in enumerate(valid_downloads)
        ]
        
        results = await asyncio.gather(*conversion_tasks, return_exceptions=True)
        converted_files = []
        for file, result in zip(valid_downloads, results):
            if isinstance(result, Exception):
                logger.error(f"Conversion failed for {file}: {result}")
                if task_id:
                    progress_state[task_id]["failed_files"].append(f"Conversion failed: {os.path.basename(file)}")
            elif result:
                converted_files.append(result)
        
        # Update for upload phase
        update_progress(task_id,
                       overall_progress=70,
                       current_phase="uploading",
                       files_completed=0,  # Reset for this phase
                       details=f"Converted {len(converted_files)} files. Starting parallel uploads...")

        # Upload files in parallel
        upload_tasks = [
            upload_file(file, refresh_token, task_id, i, len(converted_files), i) 
            for i, file in enumerate(converted_files)
        ]
        await asyncio.gather(*upload_tasks, return_exceptions=True)
        
        # Final summary
        failed_count = len(progress_state[task_id]["failed_files"])
        success_count = len(progress_state[task_id]["completed_uploads"])
        
        update_progress(task_id,
                       overall_progress=100,
                       current_phase="completed",
                       current_file="",
                       details=f"Processing complete! {success_count} files successful, {failed_count} failed.")

async def get_file_info(http_client: aiohttp.ClientSession, file_id: str, refresh_token: str) -> dict:
    """Get file information by ID."""
    token = await refresh_access_token(refresh_token)
    async with http_client.get(
        f"{GRAPH_API}/items/{file_id}",
        headers={"Authorization": f"Bearer {token['access_token']}"}
    ) as response:
        response.raise_for_status()
        return await response.json()

async def download_file_by_id(http_client: aiohttp.ClientSession, file_id: str, filename: str, refresh_token: str, task_id: str = None, file_index: int = 0, total_files: int = 0) -> str:
    """Download VOB file by ID from OneDrive with enhanced parallel progress tracking."""
    async with semaphore_download:
        try:
            # First get the file info to extract parent ID
            token = await refresh_access_token(refresh_token)
            async with http_client.get(
                f"{GRAPH_API}/items/{file_id}",
                headers={"Authorization": f"Bearer {token['access_token']}"}
            ) as info_response:
                info_response.raise_for_status()
                file_info = await info_response.json()
                parent_id = file_info.get('parentReference', {}).get('id', 'unknown')
                file_path = os.path.join(OUTPUT_DIR, f"{parent_id}-{filename}")
            
            if task_id:
                update_file_progress(task_id, file_path, "download", 0)
            
            # Now download the file content
            async with http_client.get(
                f"{GRAPH_API}/items/{file_id}/content",
                headers={"Authorization": f"Bearer {token['access_token']}"}
            ) as response:
                response.raise_for_status()
                
                # Use the same naming convention as the original download_file function
                #file_path = os.path.join(OUTPUT_DIR, f"{parent_id}-{filename}")
                total_size = int(response.headers.get('content-length', 0))
                
                async with aiofiles.open(file_path, 'wb') as f:
                    downloaded = 0
                    async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        
                        if task_id and total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            update_file_progress(task_id, file_path, "download", progress)
                
                if task_id:
                    update_file_progress(task_id, file_path, "download", 100, completed=True)
                
                logger.info(f"Downloaded: {file_path} (parent: {parent_id})")
                return file_path
                
        except Exception as e:
            error_msg = f"Download failed for {file_path}: {str(e)}"
            logger.error(error_msg)
            if task_id:
                progress_state[task_id]["failed_files"].append(error_msg)
            raise

# --- Semaphores ---
semaphore_download = asyncio.Semaphore(CONCURRENT["downloads"])
semaphore_upload = asyncio.Semaphore(CONCURRENT["uploads"])
semaphore_conversion = asyncio.Semaphore(CONCURRENT["conversions"])

# --- API Routes ---
@app.post("/convert")
async def convert_files(request: ConvertRequest):
    """Start conversion process for selected VOB files."""
    try:
        task_id = str(uuid.uuid4())
        # Initialize with dictionary instead of ProgressInfo object
        progress_state[task_id] = {
            "task_id": task_id,
            "overall_progress": 0,
            "current_phase": "initializing",
            "phase_progress": 0,
            "current_file": "",
            "files_completed": 0,
            "total_files": len(request.file_ids),  # Set total files immediately
            "details": f"Starting conversion process for {len(request.file_ids)} files...",
            "estimated_time_remaining": "",
            "estimated_phase_time_remaining": "",
            "start_time": time.time(),
            "phase_start_time": time.time(),
            # Parallel processing tracking
            "active_downloads": {},  # filename -> progress%
            "active_conversions": {},  # filename -> progress%
            "active_uploads": {},  # filename -> progress%
            "completed_downloads": [],
            "completed_conversions": [],
            "completed_uploads": [],
            "failed_files": []
        }

        logger.info(f"Starting conversion for {len(request.file_ids)} files: {request.file_ids}")

        # Start the background task with file IDs
        asyncio.create_task(process_selected_files(request.file_ids, request.refresh_token, task_id))
        
        return JSONResponse(content={"message": "Conversion started successfully", "task_id": task_id})
    except Exception as e:
        logger.error(f"Error starting conversion: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/progress/{task_id}")
async def get_progress(task_id: str):
    """Get detailed progress for a task."""
    if task_id in progress_state:
        progress_info = progress_state[task_id].copy()
        # Remove internal fields
        progress_info.pop("start_time", None)
        progress_info.pop("phase_start_time", None)
        return JSONResponse(content=progress_info)
    raise HTTPException(status_code=404, detail="Task ID not found")

@app.get("/items/{item_id}/children")
async def get_item_children(item_id: str, token: str):
    """Get children of a specific OneDrive item."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{GRAPH_API}/items/{item_id}/children",
                headers={"Authorization": f"Bearer {token}"}
            ) as response:
                if response.status == 401:
                    raise HTTPException(status_code=401, detail="Token expired or invalid")
                response.raise_for_status()
                data = await response.json()
                return JSONResponse(content=data)
    except aiohttp.ClientError as e:
        logger.error(f"Error fetching children for item {item_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch children: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error fetching children for item {item_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/items/{item_id}/tree")
async def get_item_tree(item_id: str, token: str):
    """Get complete folder tree structure with VOB file count."""
    try:
        async with aiohttp.ClientSession() as session:
            
            async def fetch_item_tree(current_item_id: str, path: str = "") -> dict:
                """Recursively fetch folder structure."""
                async with session.get(
                    f"{GRAPH_API}/items/{current_item_id}/children",
                    headers={"Authorization": f"Bearer {token}"}
                ) as response:
                    if response.status == 401:
                        raise HTTPException(status_code=401, detail="Token expired or invalid")
                    response.raise_for_status()
                    data = await response.json()
                    
                    items = []
                    vob_count = 0
                    
                    for item in data.get('value', []):
                        item_info = {
                            'id': item['id'],
                            'name': item['name'],
                            'type': 'folder' if 'folder' in item else 'file',
                            'size': item.get('size', 0),
                            'path': f"{path}/{item['name']}" if path else item['name'],
                            'children': [],
                            'vob_count': 0,
                            'is_vob': False
                        }
                        
                        if 'folder' in item:
                            # Recursively fetch children for folders
                            child_tree = await fetch_item_tree(item['id'], item_info['path'])
                            item_info['children'] = child_tree['items']
                            item_info['vob_count'] = child_tree['vob_count']
                            vob_count += child_tree['vob_count']
                        else:
                            # Check if it's a VOB file
                            if item['name'].lower().endswith('.vob'):
                                item_info['is_vob'] = True
                                vob_count += 1
                        
                        items.append(item_info)
                    
                    return {'items': items, 'vob_count': vob_count}
            
            result = await fetch_item_tree(item_id)
            
            return JSONResponse(content={
                'tree': result['items'],
                'total_vob_files': result['vob_count']
            })
            
    except aiohttp.ClientError as e:
        logger.error(f"Error fetching tree for item {item_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch tree: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error fetching tree for item {item_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Add these utility functions after the existing utility functions
def update_progress(task_id: str, **kwargs):
    """Update progress state with detailed information for parallel processing."""
    if task_id not in progress_state:
        progress_state[task_id] = {
            "task_id": task_id,
            "overall_progress": 0,
            "current_phase": "initializing",
            "phase_progress": 0,
            "current_file": "",
            "files_completed": 0,
            "total_files": 0,
            "details": "",
            "estimated_time_remaining": "",
            "estimated_phase_time_remaining": "",
            "start_time": time.time(),
            "phase_start_time": time.time(),
            # Parallel processing tracking
            "active_downloads": {},  # filename -> progress%
            "active_conversions": {},  # filename -> progress%
            "active_uploads": {},  # filename -> progress%
            "completed_downloads": [],
            "completed_conversions": [],
            "completed_uploads": [],
            "failed_files": []
        }
    
    # Update phase_start_time when phase changes
    if "current_phase" in kwargs and kwargs["current_phase"] != progress_state[task_id]["current_phase"]:
        progress_state[task_id]["phase_start_time"] = time.time()
        # Clear time estimates when switching phases
        progress_state[task_id]["estimated_phase_time_remaining"] = ""
        progress_state[task_id]["estimated_time_remaining"] = ""
    
    progress_state[task_id].update(kwargs)
    
    # Calculate phase progress and files_completed based on active operations
    if progress_state[task_id]["current_phase"] == "downloading":
        active = progress_state[task_id]["active_downloads"]
        completed = len(progress_state[task_id]["completed_downloads"])
        total = progress_state[task_id]["total_files"]
        progress_state[task_id]["files_completed"] = completed
        if total > 0:
            # Average progress of active downloads + completed downloads
            active_progress = sum(active.values()) / len(active) if active else 0
            phase_progress = int(((completed + (len(active) * active_progress / 100)) / total) * 100)
            progress_state[task_id]["phase_progress"] = min(phase_progress, 100)
            # Overall progress: 5% discovery + 30% downloading
            progress_state[task_id]["overall_progress"] = 5 + int(phase_progress * 0.30)
    
    elif progress_state[task_id]["current_phase"] == "converting":
        active = progress_state[task_id]["active_conversions"]
        completed = len(progress_state[task_id]["completed_conversions"])
        total = progress_state[task_id]["total_files"]  # Use the original total, not just downloaded files
        progress_state[task_id]["files_completed"] = completed
        if total > 0:
            active_progress = sum(active.values()) / len(active) if active else 0
            phase_progress = int(((completed + (len(active) * active_progress / 100)) / total) * 100)
            progress_state[task_id]["phase_progress"] = min(phase_progress, 100)
            # Overall progress: 35% previous + 40% converting
            progress_state[task_id]["overall_progress"] = 35 + int(phase_progress * 0.40)
    
    elif progress_state[task_id]["current_phase"] == "uploading":
        active = progress_state[task_id]["active_uploads"]
        completed = len(progress_state[task_id]["completed_uploads"])
        total = progress_state[task_id]["total_files"]  # Use the original total, not just converted files
        progress_state[task_id]["files_completed"] = completed
        if total > 0:
            active_progress = sum(active.values()) / len(active) if active else 0
            phase_progress = int(((completed + (len(active) * active_progress / 100)) / total) * 100)
            progress_state[task_id]["phase_progress"] = min(phase_progress, 100)
            # Overall progress: 75% previous + 25% uploading
            progress_state[task_id]["overall_progress"] = 75 + int(phase_progress * 0.25)
    
    # Improved time estimation - separate phase and total estimates
    current_phase = progress_state[task_id]["current_phase"]
    phase_progress = progress_state[task_id]["phase_progress"]
    overall_progress = progress_state[task_id]["overall_progress"]
    
    # Calculate phase time remaining (more accurate for immediate feedback)
    if phase_progress > 10 and current_phase != "completed":  # Only estimate after meaningful progress in current phase
        phase_elapsed = time.time() - progress_state[task_id]["phase_start_time"]
        estimated_phase_total = phase_elapsed * 100 / phase_progress
        phase_remaining = estimated_phase_total - phase_elapsed
        if phase_remaining > 0:
            progress_state[task_id]["estimated_phase_time_remaining"] = format_time(phase_remaining)
        else:
            progress_state[task_id]["estimated_phase_time_remaining"] = "Almost done..."
    elif phase_progress <= 10 and current_phase != "completed":
        progress_state[task_id]["estimated_phase_time_remaining"] = "Calculating..."
    elif current_phase == "completed":
        progress_state[task_id]["estimated_phase_time_remaining"] = ""
    
    # Calculate total time remaining (more conservative, based on historical data)
    if current_phase == "uploading":
        # In final phase, use phase ETA as total ETA
        progress_state[task_id]["estimated_time_remaining"] = progress_state[task_id]["estimated_phase_time_remaining"]
    elif overall_progress > 15 and current_phase != "completed":  # Only estimate after significant overall progress
        total_elapsed = time.time() - progress_state[task_id]["start_time"]
        
        # Use a more conservative approach based on actual progress
        if current_phase == "downloading":
            # We're still downloading, estimate conservatively
            estimated_total = total_elapsed * 100 / overall_progress * 1.2  # 20% buffer
        elif current_phase == "converting":
            # Converting usually takes longest, be more conservative
            estimated_total = total_elapsed * 100 / overall_progress * 1.3  # 30% buffer
        else:
            estimated_total = total_elapsed * 100 / overall_progress * 1.2
        
        total_remaining = estimated_total - total_elapsed
        if total_remaining > 0:
            progress_state[task_id]["estimated_time_remaining"] = format_time(total_remaining)
        else:
            progress_state[task_id]["estimated_time_remaining"] = "Almost done..."
    elif overall_progress <= 15 and current_phase != "completed":
        progress_state[task_id]["estimated_time_remaining"] = "Calculating..."
    elif current_phase == "completed":
        progress_state[task_id]["estimated_time_remaining"] = ""
    
    # Update current file info for display
    active_files = []
    if progress_state[task_id]["active_downloads"]:
        active_files.extend([f"⬇️ {f}" for f in progress_state[task_id]["active_downloads"].keys()])
    if progress_state[task_id]["active_conversions"]:
        active_files.extend([f"🔄 {f}" for f in progress_state[task_id]["active_conversions"].keys()])
    if progress_state[task_id]["active_uploads"]:
        active_files.extend([f"⬆️ {f}" for f in progress_state[task_id]["active_uploads"].keys()])
    
    if active_files:
        progress_state[task_id]["current_file"] = ", ".join(active_files[:3])  # Show max 3 files
        if len(active_files) > 3:
            progress_state[task_id]["current_file"] += f" (+{len(active_files) - 3} more)"
    
   # logger.info(f"Progress Update - Task: {task_id}, Phase: {current_phase}, "
   #            f"Overall: {overall_progress}%, "
   #            f"Phase: {progress_state[task_id]['phase_progress']}%, "
   #            f"Files: {progress_state[task_id]['files_completed']}/{progress_state[task_id]['total_files']}, "
   #            f"Active: {len(active_files)} files")

def update_file_progress(task_id: str, filename: str, operation: str, progress: int, completed: bool = False):
    """Update progress for a specific file operation."""
    if task_id not in progress_state:
        return
    
    state = progress_state[task_id]
    
    if operation == "download":
        if completed:
            state["active_downloads"].pop(filename, None)
            if filename not in state["completed_downloads"]:
                state["completed_downloads"].append(filename)
        else:
            state["active_downloads"][filename] = progress
    
    elif operation == "convert":
        if completed:
            state["active_conversions"].pop(filename, None)
            if filename not in state["completed_conversions"]:
                state["completed_conversions"].append(filename)
        else:
            state["active_conversions"][filename] = progress
    
    elif operation == "upload":
        if completed:
            state["active_uploads"].pop(filename, None)
            if filename not in state["completed_uploads"]:
                state["completed_uploads"].append(filename)
        else:
            state["active_uploads"][filename] = progress
    
    # Trigger progress update to recalculate phase progress
    update_progress(task_id)

def format_time(seconds: float) -> str:
    """Format seconds into human readable time."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"