"""Pydantic models for API requests and responses."""
from pydantic import BaseModel

class ConvertRequest(BaseModel):
    """Request model for file conversion."""
    refresh_token: str
    file_ids: list[str]

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