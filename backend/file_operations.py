"""File download and upload operations for OneDrive integration."""
import os
import asyncio
import logging
import aiofiles
import aiohttp
from fastapi import HTTPException
from tqdm.asyncio import tqdm as tqdm_asyncio
from config import GRAPH_API, CHUNK_SIZE, RETRIES_PER_CHUNK, OUTPUT_DIR
from utils import refresh_access_token
from progress import update_file_progress, progress_state

logger = logging.getLogger(__name__)

async def download_file_by_id(http_client: aiohttp.ClientSession, file_id: str, filename: str, refresh_token: str, semaphore_download, task_id: str = None, file_index: int = 0, total_files: int = 0, session_id: str = None) -> str:
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
                
                # Use session_id in path if provided
                if session_id:
                    session_dir = os.path.join(OUTPUT_DIR, session_id)
                    os.makedirs(session_dir, exist_ok=True)  # Create directory if it doesn't exist
                    file_path = os.path.join(session_dir, f"{parent_id}-{filename}")
                else:
                    file_path = os.path.join(OUTPUT_DIR, f"{parent_id}-{filename}")
            
            if task_id:
                update_file_progress(task_id, file_path, "download", 0)
            
            # Now download the file content
            async with http_client.get(
                f"{GRAPH_API}/items/{file_id}/content",
                headers={"Authorization": f"Bearer {token['access_token']}"}
            ) as response:
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                
                # Setup tqdm progress bar for terminal output
                bar_args = {
                    "total": total_size,
                    "unit": "B",
                    "unit_scale": True,
                    "unit_divisor": 1024,
                    "desc": f"Downloading {filename}",
                    "position": file_index,
                    "mininterval": 0.1,
                    "smoothing": 0.05,
                    "leave": True
                }
                
                with tqdm_asyncio(**bar_args) as progress_bar:
                    async with aiofiles.open(file_path, 'wb') as f:
                        downloaded = 0
                        async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            progress_bar.update(len(chunk))
                            
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

async def upload_file(file_path: str, refresh_token: str, semaphore_upload, task_id: str = None, file_index: int = 0, total_files: int = 0, position: int = 0) -> str:
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

async def get_file_info(http_client: aiohttp.ClientSession, file_id: str, refresh_token: str) -> dict:
    """Get file information by ID."""
    token = await refresh_access_token(refresh_token)
    async with http_client.get(
        f"{GRAPH_API}/items/{file_id}",
        headers={"Authorization": f"Bearer {token['access_token']}"}
    ) as response:
        response.raise_for_status()
        return await response.json() 