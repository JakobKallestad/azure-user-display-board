"""Configuration settings and constants."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Environment Variables ---
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# --- Directory Constants ---
OUTPUT_DIR = "vob_files"
MP4_OUTPUT_DIR = "mp4_files"
LOG_DIR = "logs"

# --- API Constants ---
AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_API = "https://graph.microsoft.com/v1.0/me/drive"
SCOPE = "https://graph.microsoft.com/.default openid profile offline_access"

# --- Processing Constants ---
CONCURRENT = {"downloads": 3, "uploads": 3, "conversions": 3}
CHUNK_SIZE = 62_914_560  # 60 MB
RETRIES_PER_CHUNK = 5

# --- FFmpeg Constants ---
FFMPEG_BASE = ["ffmpeg", "-y", "-fflags", "+genpts"]

# # GPU Encoding
# FFMPEG_ENCODE = [
#     "-c:v", "h264_nvenc", "-preset", "p2", "-b:v", "5M",
#     "-vf", "scale=1280:720", "-r", "30",
#     "-c:a", "aac", "-b:a", "128k",
#     "-progress", "pipe:2",
# ]

# CPU Encoding
FFMPEG_ENCODE = [
    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "29",
    "-vf", "scale=1280:720",
    "-c:a", "aac", "-b:a", "128k",
    "-progress", "pipe:2",
    "-threads", "0"
]

FFPROBE_BASE = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=nb_frames", "-of", "json"] 