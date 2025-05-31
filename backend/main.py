"""FastAPI application to convert VOB files from OneDrive to MP4 and upload them back."""
import os
import uuid
import time
import asyncio
import logging
import aiohttp
import shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import OUTPUT_DIR, MP4_OUTPUT_DIR, LOG_DIR, CONCURRENT, GRAPH_API
from models import ConvertRequest
from utils import refresh_access_token
from progress import progress_state, update_progress
from processing import process_selected_files

# --- Setup ---
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
    allow_origins=["http://localhost:3000", "http://frontend:80"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Session Management ---
user_sessions = {}  # session_id -> session_data

def get_or_create_session(session_id: str = None) -> str:
    """Get existing session or create new one."""
    if session_id and session_id in user_sessions:
        user_sessions[session_id]['last_activity'] = time.time()
        return session_id
    
    new_session_id = str(uuid.uuid4())
    
    user_sessions[new_session_id] = {
        'created_at': time.time(),
        'last_activity': time.time()
    }
    
    logger.info(f"Created new session: {new_session_id}")
    return new_session_id

def cleanup_session(session_id: str):
    """Clean up session directories and data."""
    if session_id in user_sessions:
        # Clean up directories
        try:
            session_dir = os.path.join(OUTPUT_DIR, session_id)
            mp4_session_dir = os.path.join(MP4_OUTPUT_DIR, session_id)
            
            if os.path.exists(session_dir):
                shutil.rmtree(session_dir)
            if os.path.exists(mp4_session_dir):
                shutil.rmtree(mp4_session_dir)
        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {e}")
        
        # Remove from sessions
        del user_sessions[session_id]
        logger.info(f"Cleaned up session: {session_id}")

# --- Semaphores (per session) ---
def get_session_semaphores(session_id: str):
    """Get or create semaphores for a session."""
    if session_id not in user_sessions:
        raise ValueError(f"Session {session_id} not found")
    
    if 'semaphores' not in user_sessions[session_id]:
        user_sessions[session_id]['semaphores'] = {
            'download': asyncio.Semaphore(CONCURRENT["downloads"]),
            'upload': asyncio.Semaphore(CONCURRENT["uploads"]),
            'conversion': asyncio.Semaphore(CONCURRENT["conversions"])
        }
    
    return user_sessions[session_id]['semaphores']

# --- API Routes ---
@app.post("/session")
async def create_session():
    """Create a new user session."""
    session_id = get_or_create_session()
    return JSONResponse(content={"session_id": session_id})

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a user session."""
    cleanup_session(session_id)
    return JSONResponse(content={"message": "Session deleted successfully"})

@app.post("/convert")
async def convert_files(request: ConvertRequest, x_session_id: str = Header(None)):
    """Start conversion process for selected VOB files."""
    try:
        # Get or create session
        session_id = get_or_create_session(x_session_id)
        
        task_id = str(uuid.uuid4())
        # Initialize with dictionary instead of ProgressInfo object
        progress_state[task_id] = {
            "task_id": task_id,
            "session_id": session_id,
            "overall_progress": 0,
            "current_phase": "initializing",
            "phase_progress": 0,
            "current_file": "",
            "files_completed": 0,
            "total_files": len(request.file_ids),
            "details": f"Starting conversion process for {len(request.file_ids)} files...",
            "estimated_time_remaining": "",
            "estimated_phase_time_remaining": "",
            "start_time": time.time(),
            "phase_start_time": time.time(),
            # Enhanced parallel processing tracking
            "active_downloads": {},  # filename -> progress (0-100)
            "active_conversions": {},  # filename -> progress (0-100)
            "active_uploads": {},  # filename -> progress (0-100)
            "completed_downloads": [],
            "completed_conversions": [],
            "completed_uploads": [],
            "failed_files": [],
        }

        logger.info(f"Starting conversion for {len(request.file_ids)} files in session {session_id}: {request.file_ids}")

        # Get session-specific semaphores
        semaphores = get_session_semaphores(session_id)
        
        # Start the background task with just session_id
        asyncio.create_task(process_selected_files(
            request.file_ids, 
            request.refresh_token, 
            task_id, 
            semaphores,
            session_id
        ))
        
        return JSONResponse(content={
            "message": "Conversion started successfully", 
            "task_id": task_id,
            "session_id": session_id
        })
    except Exception as e:
        logger.error(f"Error starting conversion: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/progress/{task_id}")
async def get_progress(task_id: str, x_session_id: str = Header(None)):
    """Get conversion progress for a specific task."""
    if task_id not in progress_state:
        raise HTTPException(status_code=404, detail="Task not found")
    
    progress_data = progress_state[task_id]
    
    # Verify session if provided
    #if x_session_id and progress_data.get("session_id") != x_session_id:
    #    raise HTTPException(status_code=403, detail="Task does not belong to this session")
    
    return JSONResponse(content=progress_data)

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

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "VOB Converter API is running", "status": "healthy"}

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}