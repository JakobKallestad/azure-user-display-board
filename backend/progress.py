"""Progress tracking functionality for parallel processing."""
import time
from utils import format_time

# Enhanced progress state to store detailed information
progress_state = {}  # Task ID -> ProgressInfo dict

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