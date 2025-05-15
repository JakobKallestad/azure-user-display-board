from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aiohttp
import aiofiles
import os
import asyncio
import subprocess
import logging
from tqdm import tqdm
from dotenv import load_dotenv
import uuid

# Load environment variables from .env file
load_dotenv()

# Get client_id and client_secret from environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
SCOPE = "https://graph.microsoft.com/.default openid profile offline_access"

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS configuration
origins = [
    "http://localhost:3000",  # Adjust this to your frontend URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConvertRequest(BaseModel):
    token: str
    refresh_token: str  # Add refresh token to the request model

output_dir = "vob_files"
mp4_output_dir = "mp4_files"
CONCURRENT_DOWNLOADS = 3
CONCURRENT_UPLOADS = 5

semaphore_download = asyncio.Semaphore(CONCURRENT_DOWNLOADS)
semaphore_upload = asyncio.Semaphore(CONCURRENT_UPLOADS)

# Shared state for progress tracking
progress_state = {}

async def refresh_access_token(refresh_token: str):
    async with aiohttp.ClientSession() as session:
        response = await session.post(
            TOKEN_URL,
            data={
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'scope': SCOPE,
            }
        )
        response_data = await response.json()
        logger.info(refresh_token)
        logger.info(f"Token refresh response: {response.status}, {response_data}")  # Log the response
        if response.status != 200:
            raise HTTPException(status_code=response.status, detail="Failed to refresh token")
        return response_data['access_token']  # Return the new access token

async def download_file(http_client, item_id, item_name, item_parent_id, refresh_token):
    async with semaphore_download:
        try:
            token = await refresh_access_token(refresh_token)  # Get a new access token
            async with http_client.get(
                url=f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/content",
                headers={"Authorization": f"Bearer {token}"}
            ) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("Content-Length", 0))
                file_path = os.path.join(output_dir, f"{item_parent_id}-{item_name}")
                os.makedirs(output_dir, exist_ok=True)

                chunk_size = 32768
                downloaded_size = 0

                with tqdm(total=total_size, unit="B", unit_scale=True, unit_divisor=1024, desc=f"Downloading {item_name}") as progress_bar:
                    async with aiofiles.open(file_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            if chunk:
                                await f.write(chunk)
                                downloaded_size += len(chunk)
                                progress_bar.update(len(chunk))

                logger.info(f"Downloaded {item_name} successfully.")
                return file_path
        except aiohttp.ClientError as e:
            logger.error(f"Error downloading {item_name}: {e}")
            raise HTTPException(status_code=500, detail=f"Error downloading {item_name}: {e}")

async def convert_vob_to_mp4(input_file):
    output_file = input_file[:-4] + ".mp4"
    command = [
        'ffmpeg', '-y', '-i', input_file,
        '-c:v', 'libx264', '-c:a', 'aac', output_file
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in process.stderr:
        logger.info(line)
    logger.info(f"Converted {input_file} to {output_file}.")
    return output_file

async def upload_file(file_path, refresh_token):
    async with semaphore_upload:
        try:
            token = await refresh_access_token(refresh_token)  # Get a new access token
            item_parent_id, filename = os.path.basename(file_path).split("-")
            async with aiohttp.ClientSession() as http_client:
                request_body = {
                    "item": {
                        "description": "Converted MP4 file",
                        "name": filename
                    }
                }
                async with http_client.post(
                    url=f"https://graph.microsoft.com/v1.0/me/drive/items/{item_parent_id}:/{filename}:/createUploadSession",
                    headers={"Authorization": f"Bearer {token}"},
                    json=request_body
                ) as response_upload_session:
                    response_upload_session.raise_for_status()
                    upload_url = (await response_upload_session.json())["uploadUrl"]

                async with aiofiles.open(file_path, 'rb') as upload:
                    total_file_size = os.path.getsize(file_path)
                    chunk_size = 327680
                    chunk_number = (total_file_size + chunk_size - 1) // chunk_size

                    for counter in tqdm(range(chunk_number), desc=f"Uploading {filename}"):
                        chunk_data = await upload.read(chunk_size)
                        start_index = counter * chunk_size
                        end_index = start_index + len(chunk_data)

                        headers = {
                            "Content-Length": f"{len(chunk_data)}",
                            "Content-Range": f"bytes {start_index}-{end_index - 1}/{total_file_size}"
                        }

                        async with http_client.put(upload_url, headers=headers, data=chunk_data) as response:
                            response.raise_for_status()
                logger.info(f"Uploaded {filename} successfully.")
                return filename
        except Exception as e:
            logger.error(f"Error uploading {file_path}: {e}")
            raise HTTPException(status_code=500, detail=f"Error uploading {file_path}: {e}")

async def find_vob_files(http_client, item_ids, refresh_token):
    final_item_ids = []
    new_item_ids = []
    token = await refresh_access_token(refresh_token)

    while item_ids:
        for item_id in item_ids:
            async with http_client.get(
                url=f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/children",
                headers={"Authorization": f"Bearer {token}"}
            ) as response:
                response.raise_for_status()
                msg = await response.json()
                items = msg["value"]

            for item in items:
                if item["name"].endswith(".VOB"):
                    final_item_ids.append((item["id"], item["name"], item["parentReference"]["id"]))
                elif "file" not in item:
                    new_item_ids.append(item["id"])
        item_ids = new_item_ids
        new_item_ids = []

    logger.info(f"Found {len(final_item_ids)} VOB files.")
    return final_item_ids

async def process_files(item_ids, refresh_token, task_id):
    progress_state[task_id] = 0  # Initialize progress
    async with aiohttp.ClientSession() as http_client:
        # Find all VOB files
        final_item_ids = await find_vob_files(http_client, item_ids, refresh_token)
        final_item_ids = final_item_ids[:3]

        # Download files
        download_tasks = [download_file(http_client, item_id, item_name, item_parent_id, refresh_token) for item_id, item_name, item_parent_id in final_item_ids]
        downloaded_files = await asyncio.gather(*download_tasks)

        # Update progress
        progress_state[task_id] = 50  # 50% after download

        # Convert files
        conversion_tasks = [convert_vob_to_mp4(file) for file in downloaded_files]
        converted_files = await asyncio.gather(*conversion_tasks)

        # Update progress
        progress_state[task_id] = 75  # 75% after conversion

        # Upload files
        upload_tasks = [upload_file(file, refresh_token) for file in converted_files]
        await asyncio.gather(*upload_tasks)

        # Complete progress
        progress_state[task_id] = 100  # 100% when done

@app.post("/convert")
async def convert_files(request: ConvertRequest):
    try:
        # Initialize a unique task_id for tracking progress
        task_id = str(uuid.uuid4())  # Generate a unique task ID
        progress_state[task_id] = 0  # Initialize progress state for this task
        print(task_id)
        print(type(request.refresh_token))

        item_ids = ["47575C443A523D3A!76020"]  # Replace with your logic to get item IDs
        await process_files(item_ids, request.refresh_token, task_id)
        return JSONResponse(content={"message": "Files processed successfully."})
    except Exception as e:
        logger.error(f"Error processing files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/progress/{task_id}")
async def get_progress(task_id: str):
    if task_id in progress_state:
        return JSONResponse(content={"task_id": task_id, "progress": progress_state[task_id]})
    else:
        raise HTTPException(status_code=404, detail="Task ID not found")