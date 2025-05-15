from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import aiohttp

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

@app.get("/items/{item_id}/children")
async def get_children(item_id: str, token: str):
    url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/children"
    
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                raise HTTPException(status_code=response.status, detail="Error fetching data from Microsoft Graph API")
            data = await response.json()
            return data