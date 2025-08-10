"""Main processing pipeline for VOB to MP4 conversion."""
import os
import asyncio
import logging
import aiohttp
from progress import update_progress, progress_state
from credits import refund_credits_on_failure
from file_operations import download_file_by_id, upload_file, get_file_info
from video_processing import convert_vob_to_mp4

logger = logging.getLogger(__name__)

async def process_selected_files(file_ids: list[str], refresh_token: str, task_id: str, semaphores: dict, session_id: str) -> None:
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
        
        # Download files in parallel - pass session_id
        download_tasks = [
            download_file_by_id(http_client, file_id, info['name'], refresh_token, semaphores['download'], task_id, i, total_files, session_id=session_id)
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

        # Convert files in parallel - pass session_id
        conversion_tasks = [
            convert_vob_to_mp4(file, semaphores['conversion'], task_id, i, len(valid_downloads), i, session_id=session_id) 
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
            upload_file(file, refresh_token, semaphores['upload'], task_id, i, len(converted_files), i) 
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

        # Handle processing failure and refund credits if needed
        await handle_processing_failure(task_id, f"Processing failed: {failed_count} files failed.")

async def handle_processing_failure(task_id: str, error_message: str):
    """Handle processing failure and refund credits if needed."""
    try:
        if task_id in progress_state:
            progress_data = progress_state[task_id]
            user_id = progress_data.get("user_id")
            estimated_cost = progress_data.get("estimated_cost")
            
            if user_id and estimated_cost:
                logger.info(f"Processing failed for task {task_id}, initiating refund")
                await refund_credits_on_failure(user_id, estimated_cost, task_id)
            
            # Update progress to show failure
            update_progress(task_id, 
                current_phase="failed",
                details=f"Processing failed: {error_message}",
                overall_progress=0
            )
    except Exception as e:
        logger.error(f"Error handling processing failure: {e}")