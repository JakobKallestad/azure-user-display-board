"""FastAPI application to convert VOB files from OneDrive to MP4 and upload them back."""
import os
import uuid
import time
import asyncio
import logging
import aiohttp
import shutil
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from decimal import Decimal
from credits import add_user_credits as credits_add_user_credits
from datetime import datetime

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
    allow_origins=["http://localhost:3000", "http://frontend:80", "https://driver-461415.web.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- Stripe ---
import stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")  # Price for $1 credit top-up
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    logger.warning("Stripe not configured; payment endpoints will be disabled")

# --- Session Management ---
user_sessions = {}  # session_id -> session_data

# Add Supabase configuration after other imports
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")  # Service role key for admin operations

if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
else:
    supabase = None
    logger.warning("Supabase configuration missing. Credit system will be disabled.")

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

@app.post("/payments/create-checkout-session")
async def create_checkout_session(user_id: str, amount: float = 1.0):
    """Create a Stripe Checkout Session to top up credits."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Payments not configured")
    try:
        line_items = []
        if STRIPE_PRICE_ID:
            line_items = [{
                'price': STRIPE_PRICE_ID,
                'quantity': int(max(1, round(amount)))
            }]
        else:
            line_items = [{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': 'Credit top-up'},
                    'unit_amount': int(amount * 100)
                },
                'quantity': 1
            }]

        session = stripe.checkout.Session.create(
            mode='payment',
            line_items=line_items,
            success_url=os.getenv('PAYMENT_SUCCESS_URL', 'http://localhost:3000') + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=os.getenv('PAYMENT_CANCEL_URL', 'http://localhost:3000'),
            metadata={'user_id': user_id, 'topup_amount': str(amount)}
        )
        return { 'checkout_url': session.url }
    except Exception as e:
        logger.error(f"Failed to create checkout session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")

@app.post("/payments/webhook")
async def stripe_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook not configured")
    try:
        payload = await request.body()
        sig_header = request.headers.get('stripe-signature')
        logger.info("Stripe webhook hit. signature header present=%s length=%s", bool(sig_header), len(payload))
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        logger.info("Stripe event verified id=%s type=%s", event.get('id'), event.get('type'))
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_id = event.get('id')
    if event.get('type') in ('checkout.session.completed',):
        session_obj = event.get('data', {}).get('object', {}) or {}
        metadata = session_obj.get('metadata') or {}
        user_id = metadata.get('user_id')
        amount_str = metadata.get('topup_amount', '1.0')
        try:
            amount = float(amount_str)
        except Exception:
            amount = 1.0

        logger.info("Stripe checkout completed metadata user_id=%s amount=%s", user_id, amount)

        if user_id and event_id:
            # Idempotency check: has this event already been processed ?
            try:
                existing = supabase.table("credit_transactions").select("id").eq("event_id", event_id).eq("transaction_type", "stripe_topup").execute()
                if existing.data and len(existing.data) > 0:
                    logger.info(f"Stripe event {event_id} already processed, skipping credit addition.")
                    return { 'received': True, 'idempotent': True }
            except Exception as e:
                logger.error(f"Error checking idempotency for event {event_id}: {e}")
                # If check fails, still proceed to avoid blocking real payments

            try:
                # Add credits and log event_id for idempotency
                await credits_add_user_credits(user_id, amount, description='Stripe top-up', event_id=event_id, transaction_type='stripe_topup')
                logger.info("Credits updated for user %s by $%s", user_id, amount)
            except Exception as e:
                logger.error("Failed to add credits after payment: %r", e)
        else:
            logger.warning("Stripe session metadata missing user_id or event_id; skipping credit update")
    else:
        logger.info("Ignoring Stripe event type %s", event.get('type'))

    return { 'received': True }

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a user session."""
    cleanup_session(session_id)
    return JSONResponse(content={"message": "Session deleted successfully"})

@app.post("/convert")
async def convert_files(request: ConvertRequest, x_session_id: str = Header(None)):
    """Start conversion process for selected VOB files."""
    try:
        # Add debugging logs
        logger.info(f"Received conversion request: user_id={request.user_id}, file_ids={request.file_ids}, estimated_cost={request.estimated_cost}")
        logger.info(f"Number of files to process: {len(request.file_ids)}")
        
        # Validate user has sufficient credits and deduct them
        if supabase and request.estimated_cost:
            logger.info(f"Processing credit deduction for user {request.user_id}")
            try:
                # Get current user credits
                credits_response = supabase.table("user_credits").select("*").eq("user_id", request.user_id).execute()
                logger.info(f"Credits response: {credits_response.data}")
                
                if not credits_response.data:
                    logger.error(f"No credits found for user {request.user_id}")
                    raise HTTPException(status_code=400, detail="User credits not found")
                
                current_credits = Decimal(str(credits_response.data[0]["credits"]))
                estimated_cost = Decimal(str(request.estimated_cost))
                
                logger.info(f"Current credits: ${current_credits}, Estimated cost: ${estimated_cost}")
                
                if current_credits < estimated_cost:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Insufficient credits. Need ${estimated_cost}, have ${current_credits}"
                    )
                
                # Deduct credits atomically
                new_credits = current_credits - estimated_cost
                
                logger.info(f"Deducting ${estimated_cost} from user {request.user_id}")
                update_response = supabase.table("user_credits").update({
                    "credits": float(new_credits),
                    "updated_at": "now()"
                }).eq("user_id", request.user_id).execute()
                
                logger.info(f"Credit update result: {update_response}")
                
                # Try to log the transaction, but don't fail if the table doesn't exist
                try:
                    transaction_response = supabase.table("credit_transactions").insert({
                        "user_id": request.user_id,
                        "deducted_amount": float(estimated_cost),
                        "previous_credits": float(current_credits),
                        "new_credits": float(new_credits),
                        "remaining_credits": float(new_credits),
                        "transaction_type": "debit",
                        "description": f"Conversion of {len(request.file_ids)} VOB files",
                        "updated_at": "now()"
                    }).execute()
                    logger.info(f"Transaction logged: {transaction_response}")
                except Exception as transaction_error:
                    logger.warning(f"Failed to log transaction (table may not exist): {transaction_error}")
                    # Continue without failing - transaction logging is optional
                
            except Exception as credit_error:
                logger.error(f"Credit deduction failed: {credit_error}")
                raise HTTPException(status_code=400, detail="Credit deduction failed")
        else:
            logger.warning(f"Skipping credit deduction - supabase: {supabase is not None}, estimated_cost: {request.estimated_cost}")
        
        # Get or create session
        session_id = get_or_create_session(x_session_id)
        logger.info(f"Using session_id: {session_id}")
        
        task_id = str(uuid.uuid4())
        logger.info(f"Generated task_id: {task_id}")
        
        # Initialize with dictionary instead of ProgressInfo object - KEEP ALL EXISTING FIELDS
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
            # Add credit tracking for potential refunds
            "user_id": request.user_id,
            "estimated_cost": request.estimated_cost,
        }

        logger.info(f"Initialized progress state for task {task_id}")
        logger.info(f"Starting conversion for {len(request.file_ids)} files in session {session_id}: {request.file_ids}")

        # Get session-specific semaphores
        semaphores = get_session_semaphores(session_id)
        
        # Start the background task with just session_id
        logger.info(f"Starting background processing task")
        asyncio.create_task(process_selected_files(
            request.file_ids, 
            request.refresh_token, 
            task_id, 
            semaphores,
            session_id
        ))

        logger.info(f"Conversion request processed successfully. Returning task_id: {task_id}, session_id: {session_id}")
        return {"task_id": task_id, "session_id": session_id}
        
    except HTTPException:
        logger.error(f"Error - something went wrong")
        raise
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

def calculate_processing_estimates(total_size_bytes: int) -> dict:
    """Calculate processing time and cost estimates based on file size."""
    total_size_gb = total_size_bytes / (1024 ** 3)  # Convert to GB
    
    # 300MB takes 45 minutes, so 1GB takes 150 minutes (2.5 hours)
    minutes_per_gb = 2.7
    # DEBUG
    estimated_minutes = total_size_gb * minutes_per_gb
    
    # Cost: $1 per GB
    estimated_cost = total_size_gb * 1.0
    
    return {
        "total_size_bytes": total_size_bytes,
        "total_size_gb": round(total_size_gb, 2),
        "estimated_minutes": round(estimated_minutes, 1),
        "estimated_cost": round(estimated_cost, 2)
    }

@app.get("/items/{item_id}/tree")
async def get_item_tree(item_id: str, token: str):
    """Get complete folder tree structure with VOB file count and size calculations."""
    try:
        async with aiohttp.ClientSession() as session:
            async def fetch_item_tree(current_item_id: str, path: str = "") -> dict:
                """Recursively fetch folder structure."""
                async with session.get(
                    f"{GRAPH_API}/items/{current_item_id}/children",
                    headers={"Authorization": f"Bearer {token}"}
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    items = []
                    vob_count = 0
                    total_vob_size = 0  # Add total size tracking
                    
                    for item in data.get('value', []):
                        item_info = {
                            'id': item['id'],
                            'name': item['name'],
                            'type': 'folder' if 'folder' in item else 'file',
                            'size': item.get('size', 0),
                            'path': f"{path}/{item['name']}" if path else item['name'],
                            'children': [],
                            'vob_count': 0,
                            'vob_size': 0,  # Add vob_size field
                            'is_vob': False
                        }
                        
                        if 'folder' in item:
                            # Recursively fetch children for folders
                            child_tree = await fetch_item_tree(item['id'], item_info['path'])
                            item_info['children'] = child_tree['items']
                            item_info['vob_count'] = child_tree['vob_count']
                            item_info['vob_size'] = child_tree['total_vob_size']
                            vob_count += child_tree['vob_count']
                            total_vob_size += child_tree['total_vob_size']
                        else:
                            # Check if it's a VOB file
                            if item['name'].lower().endswith('.vob'):
                                item_info['is_vob'] = True
                                item_info['vob_size'] = item.get('size', 0)
                                vob_count += 1
                                total_vob_size += item.get('size', 0)
                        
                        items.append(item_info)
                    
                    return {'items': items, 'vob_count': vob_count, 'total_vob_size': total_vob_size}
            
            result = await fetch_item_tree(item_id)
            
            # Calculate processing estimates
            estimates = calculate_processing_estimates(result['total_vob_size'])
            
            return JSONResponse(content={
                'tree': result['items'],
                'total_vob_files': result['vob_count'],
                'total_vob_size': result['total_vob_size'],
                'estimates': estimates
            })
            
    except aiohttp.ClientError as e:
        logger.error(f"Error fetching tree for item {item_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch tree: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error fetching tree for item {item_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/path/tree")
async def get_path_tree(path: str, token: str):
    """Get complete folder tree structure starting from a drive path like /Pictures/Folder.

    Uses Graph endpoint /me/drive/root:/path:/children recursively.
    """
    try:
        # Normalize path to start with '/'
        normalized_path = path if path.startswith("/") else f"/{path}"

        async with aiohttp.ClientSession() as session:
            async def fetch_tree_by_path(current_path: str) -> dict:
                async with session.get(
                    f"{GRAPH_API}/root:{current_path}:/children",
                    headers={"Authorization": f"Bearer {token}"}
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    items = []
                    vob_count = 0
                    total_vob_size = 0

                    for item in data.get('value', []):
                        item_path = f"{current_path}/{item['name']}" if not current_path.endswith('/') else f"{current_path}{item['name']}"
                        item_info = {
                            'id': item['id'],
                            'name': item['name'],
                            'type': 'folder' if 'folder' in item else 'file',
                            'size': item.get('size', 0),
                            'path': item_path.lstrip('/'),
                            'children': [],
                            'vob_count': 0,
                            'vob_size': 0,
                            'is_vob': False
                        }

                        if 'folder' in item:
                            child_tree = await fetch_tree_by_path(item_path)
                            item_info['children'] = child_tree['items']
                            item_info['vob_count'] = child_tree['vob_count']
                            item_info['vob_size'] = child_tree['total_vob_size']
                            vob_count += child_tree['vob_count']
                            total_vob_size += child_tree['total_vob_size']
                        else:
                            if item['name'].lower().endswith('.vob'):
                                item_info['is_vob'] = True
                                item_info['vob_size'] = item.get('size', 0)
                                vob_count += 1
                                total_vob_size += item.get('size', 0)

                        items.append(item_info)

                    return {'items': items, 'vob_count': vob_count, 'total_vob_size': total_vob_size}

            result = await fetch_tree_by_path(normalized_path)

            estimates = calculate_processing_estimates(result['total_vob_size'])

            return JSONResponse(content={
                'tree': result['items'],
                'total_vob_files': result['vob_count'],
                'total_vob_size': result['total_vob_size'],
                'estimates': estimates
            })

    except aiohttp.ClientError as e:
        logger.error(f"Error fetching tree for path {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch tree: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error fetching tree for path {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "VOB Converter API is running", "status": "healthy"}

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}

# Add these helper functions after the existing helper functions
async def get_or_create_user_credits(user_id: str) -> dict:
    """Get user credits or create with default 5.00 if doesn't exist."""
    if not supabase:
        raise HTTPException(status_code=500, detail="Credit system not configured")
    
    try:
        # Try to get existing credits
        result = supabase.table('user_credits').select('*').eq('user_id', user_id).execute()
        
        if result.data:
            return result.data[0]
        else:
            # Create new credit record with $5.00 default
            new_credit = supabase.table('user_credits').insert({
                'user_id': user_id,
                'credits': 5.00
            }).execute()
            return new_credit.data[0]
    except Exception as e:
        logger.error(f"Error managing user credits for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to manage user credits")

async def update_user_credits(user_id: str, new_amount: float) -> dict:
    """Update user credits to a new amount."""
    if not supabase:
        raise HTTPException(status_code=500, detail="Credit system not configured")
    
    try:
        result = supabase.table('user_credits').update({
            'credits': new_amount
        }).eq('user_id', user_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="User credits not found")
        
        return result.data[0]
    except Exception as e:
        logger.error(f"Error updating credits for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user credits")

async def deduct_user_credits(user_id: str, amount: float) -> dict:
    """Deduct credits from user account. Returns updated credit info."""
    if not supabase:
        raise HTTPException(status_code=500, detail="Credit system not configured")
    
    try:
        # Get current credits
        current_credits = await get_or_create_user_credits(user_id)
        current_amount = float(current_credits['credits'])
        
        if current_amount < amount:
            raise HTTPException(status_code=400, detail="Insufficient credits")
        
        new_amount = current_amount - amount
        return await update_user_credits(user_id, new_amount)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deducting credits for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to deduct credits")

# Add new endpoints after the existing endpoints
@app.get("/credits/{user_id}")
async def get_user_credits(user_id: str):
    """Get user's current credit balance."""
    try:
        credits = await get_or_create_user_credits(user_id)
        return JSONResponse(content={
            "user_id": user_id,
            "credits": float(credits['credits']),
            "updated_at": credits['updated_at']
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching credits for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user credits")

@app.post("/credits/{user_id}/add")
async def add_user_credits(user_id: str, amount: float = 1.0):
    """Add credits to user account (for testing - $1.00 default)."""
    try:
        # Get current credits
        current_credits = await get_or_create_user_credits(user_id)
        current_amount = float(current_credits['credits'])
        
        # Add the amount
        new_amount = current_amount + amount
        updated_credits = await update_user_credits(user_id, new_amount)
        
        return JSONResponse(content={
            "user_id": user_id,
            "previous_credits": current_amount,
            "added_amount": amount,
            "new_credits": float(updated_credits['credits']),
            "updated_at": updated_credits['updated_at']
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding credits for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to add credits")

@app.post("/credits/{user_id}/deduct")
async def deduct_credits_endpoint(user_id: str, amount: float):
    """Deduct credits from user account."""
    try:
        updated_credits = await deduct_user_credits(user_id, amount)
        
        return JSONResponse(content={
            "user_id": user_id,
            "deducted_amount": amount,
            "remaining_credits": float(updated_credits['credits']),
            "updated_at": updated_credits['updated_at']
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deducting credits for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to deduct credits")

async def refund_credits_on_failure(user_id: str, amount: float, task_id: str):
    """Refund credits if conversion fails."""
    if not supabase or not amount:
        return
        
    try:
        logger.info(f"Processing refund for user {user_id}: ${amount}")
        
        # Get current credits
        credits_response = supabase.table("user_credits").select("*").eq("user_id", user_id).execute()
        
        if credits_response.data:
            current_credits = Decimal(str(credits_response.data[0]["credits"]))
            refund_amount = Decimal(str(amount))
            new_credits = current_credits + refund_amount
            
            logger.info(f"Refunding ${refund_amount} to user {user_id}. Current: ${current_credits}, New: ${new_credits}")
            
            # Refund credits
            update_response = supabase.table("user_credits").update({
                "credits": float(new_credits),
                "updated_at": "now()"
            }).eq("user_id", user_id).execute()
            
            logger.info(f"Credit refund result: {update_response}")
            
            # Log refund transaction
            try:
                transaction_response = supabase.table("credit_transactions").insert({
                    "user_id": user_id,
                    "added_amount": float(refund_amount),
                    "previous_credits": float(current_credits),
                    "new_credits": float(new_credits),
                    "remaining_credits": float(new_credits),
                    "transaction_type": "credit",
                    "description": f"Refund for failed conversion (task: {task_id})",
                    "updated_at": "now()"
                }).execute()
                logger.info(f"Refund transaction logged: {transaction_response}")
            except Exception as transaction_error:
                logger.warning(f"Failed to log refund transaction: {transaction_error}")
            
            logger.info(f"Successfully refunded ${refund_amount} to user {user_id}. New balance: ${new_credits}")
            
    except Exception as e:
        logger.error(f"Failed to refund credits: {e}")