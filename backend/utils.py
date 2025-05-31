"""Utility functions for authentication and progress tracking."""
import time
import aiohttp
from fastapi import HTTPException
from config import TOKEN_URL, CLIENT_ID, CLIENT_SECRET, SCOPE

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