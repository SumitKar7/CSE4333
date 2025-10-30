"""
Storage Service - API for retrieving converted audio files
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import os
from pymongo import MongoClient
from typing import Optional

app = FastAPI(title="Storage Service", version="1.0.0")

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGODB_DB = os.getenv("MONGODB_DB", "video_converter")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/outputs"))


def get_mongo_client():
    """Get MongoDB database client."""
    client = MongoClient(MONGODB_URI)
    return client[MONGODB_DB]


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "storage_service"}


@app.get("/download/{job_id}")
async def download_audio(job_id: str):
    """
    Download the converted audio file for a given job ID.
    
    Args:
        job_id: The job identifier
        
    Returns:
        Audio file download
    """
    try:
        db = get_mongo_client()
        job = db.videos.find_one({"job_id": job_id})
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.get("status") != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Job is not completed. Current status: {job.get('status')}"
            )
        
        audio_path = job.get("audio_file_path")
        file_path = None
        if audio_path:
            candidate = Path(audio_path)
            if candidate.exists():
                file_path = candidate
        
        # Fallback: if stored path is missing or not found, try OUTPUT_DIR/{job_id}.mp3
        if file_path is None:
            fallback = OUTPUT_DIR / f"{job_id}.mp3"
            if fallback.exists():
                file_path = fallback
        
        if file_path is None:
            raise HTTPException(status_code=404, detail="Audio file not found on disk")
        
        return FileResponse(
            path=str(file_path),
            filename=f"{job_id}.mp3",
            media_type="audio/mpeg"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/job/{job_id}/info")
async def get_job_info(job_id: str):
    """Get information about a conversion job."""
    try:
        db = get_mongo_client()
        job = db.videos.find_one({"job_id": job_id})
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job.pop("_id", None)
        return job
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

