"""
Upload Service - FastAPI microservice that handles video file uploads
and queues conversion jobs in RabbitMQ.
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
import pika
import os
import uuid
from datetime import datetime
from pathlib import Path
import json
from pymongo import MongoClient
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(title="Video Upload Service", version="1.0.0")

# Static/Template setup for simple web UI
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Configuration from environment variables
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "video_conversion_queue")

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGODB_DB = os.getenv("MONGODB_DB", "video_converter")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "videodb")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Database connections
mongo_client = None
pg_conn = None


def get_mongo_client():
    global mongo_client
    if mongo_client is None:
        mongo_client = MongoClient(MONGODB_URI)
    return mongo_client[MONGODB_DB]


def get_postgres_conn():
    global pg_conn
    if pg_conn is None or pg_conn.closed:
        pg_conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
    return pg_conn


@app.on_event("startup")
async def startup():
    """Initialize database connections and create tables if needed."""
    try:
        # Initialize PostgreSQL schema
        conn = get_postgres_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversion_jobs (
                job_id VARCHAR(255) PRIMARY KEY,
                user_id VARCHAR(255),
                original_filename VARCHAR(255),
                file_path TEXT,
                status VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                audio_file_path TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS request_logs (
                id SERIAL PRIMARY KEY,
                job_id VARCHAR(255),
                action VARCHAR(100),
                details JSONB,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"Warning: Could not initialize databases: {e}")


@app.on_event("shutdown")
async def shutdown():
    """Close database connections."""
    if pg_conn and not pg_conn.closed:
        pg_conn.close()


class UploadResponse(BaseModel):
    job_id: str
    status: str
    message: str


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "upload_service"}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Simple HTML upload form UI."""
    # Inline minimal HTML if template file not present
    index_html = (TEMPLATES_DIR / "index.html")
    if index_html.exists():
        return templates.TemplateResponse("index.html", {"request": request})
    html = """
    <!doctype html>
    <html lang=\"en\">
      <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>Video → Audio Converter</title>
        <style>
          body{font-family: system-ui,-apple-system,Segoe UI,Roboto; max-width: 720px; margin: 2rem auto; padding: 0 1rem;}
          header{margin-bottom:1rem}
          .card{border:1px solid #e5e7eb; border-radius:12px; padding:1rem}
          .row{margin:.5rem 0}
          button{background:#111827;color:#fff;border:none;border-radius:8px;padding:.6rem 1rem;cursor:pointer}
          input[type=file]{padding:.5rem;border:1px solid #e5e7eb;border-radius:8px;width:100%}
          .mono{font-family: ui-monospace, SFMono-Regular, Menlo, monospace;}
          .muted{color:#6b7280}
          .ok{color:#16a34a}
          .err{color:#dc2626}
          .status{padding:.5rem 0}
        </style>
      </head>
      <body>
        <header>
          <h1>Video → Audio Converter</h1>
          <p class=\"muted\">Upload a video file; the worker will extract audio. This is a minimal demo UI.</p>
        </header>
        <section class=\"card\">
          <div class=\"row\">
            <input id=\"file\" type=\"file\" accept=\"video/*\" />
          </div>
          <div class=\"row\">
            <button id=\"uploadBtn\">Upload & Convert</button>
          </div>
          <div id=\"out\" class=\"status mono\"></div>
        </section>

        <script>
        const out = document.getElementById('out');
        const btn = document.getElementById('uploadBtn');
        const fileEl = document.getElementById('file');
        let jobId = null;

        function log(msg, cls=''){
          const p = document.createElement('div');
          if (cls) p.className = cls;
          p.textContent = msg;
          out.appendChild(p);
        }

        async function poll(jobId){
          try{
            const r = await fetch(`/job/${jobId}`);
            if(!r.ok){ log(`Status error: ${r.status}`, 'err'); return; }
            const data = await r.json();
            log(`Status: ${data.status}`);
            if(data.status === 'completed'){
              const a = document.createElement('a');
              a.href = `http://localhost:8001/download/${jobId}`;
              a.textContent = 'Download audio';
              a.target = '_blank';
              out.appendChild(a);
              log('Ready to download ✅', 'ok');
              return;
            }
            if(data.status === 'failed'){
              log(`Failed: ${data.error || 'unknown error'}`, 'err');
              return;
            }
            setTimeout(()=>poll(jobId), 2000);
          }catch(e){
            log(`Poll error: ${e}`, 'err');
          }
        }

        btn.addEventListener('click', async ()=>{
          out.innerHTML = '';
          const f = fileEl.files && fileEl.files[0];
          if(!f){ log('Choose a video file first', 'err'); return; }
          const fd = new FormData();
          fd.append('file', f);
          fd.append('user_id', 'demo-user');
          try{
            log('Uploading...');
            const r = await fetch('/upload', { method:'POST', body: fd });
            const data = await r.json();
            if(!r.ok){ log(`Upload failed: ${data.detail || r.status}`, 'err'); return; }
            jobId = data.job_id;
            log(`Queued. Job: ${jobId}`);
            poll(jobId);
          }catch(e){
            log(`Upload error: ${e}`, 'err');
          }
        });
        </script>
      </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.post("/upload", response_model=UploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None)
):
    """
    Upload a video file and queue it for conversion.
    
    Returns:
        JSON response with job_id and status
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a video file."
        )
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Save uploaded file
    file_extension = Path(file.filename).suffix
    saved_filename = f"{job_id}{file_extension}"
    file_path = UPLOAD_DIR / saved_filename
    
    try:
        # Save file
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        file_size = len(content)
        
        # Store metadata in MongoDB
        db = get_mongo_client()
        video_metadata = {
            "job_id": job_id,
            "original_filename": file.filename,
            "file_path": str(file_path),
            "file_size": file_size,
            "content_type": file.content_type,
            "user_id": user_id,
            "status": "queued",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        db.videos.insert_one(video_metadata)
        
        # Store job in PostgreSQL
        conn = get_postgres_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO conversion_jobs (job_id, user_id, original_filename, file_path, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (job_id, user_id or "anonymous", file.filename, str(file_path), "queued"))
        conn.commit()
        cur.close()
        
        # Log request in PostgreSQL
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO request_logs (job_id, action, details)
            VALUES (%s, %s, %s)
        """, (job_id, "upload", json.dumps({
            "filename": file.filename,
            "file_size": file_size,
            "content_type": file.content_type
        })))
        conn.commit()
        cur.close()
        
        # Queue job in RabbitMQ
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    credentials=credentials
                )
            )
            channel = connection.channel()
            
            # Declare queue
            channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
            
            # Publish job
            message = {
                "job_id": job_id,
                "file_path": str(file_path),
                "original_filename": file.filename,
                "user_id": user_id
            }
            
            channel.basic_publish(
                exchange="",
                routing_key=RABBITMQ_QUEUE,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                )
            )
            
            connection.close()
            
        except Exception as e:
            print(f"Warning: Could not queue job in RabbitMQ: {e}")
            # Update status to failed
            db.videos.update_one(
                {"job_id": job_id},
                {"$set": {"status": "failed", "error": str(e)}}
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to queue job: {str(e)}"
            )
        
        return UploadResponse(
            job_id=job_id,
            status="queued",
            message=f"Video uploaded successfully. Job ID: {job_id}"
        )
        
    except Exception as e:
        # Clean up on error
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a conversion job."""
    try:
        # Check MongoDB
        db = get_mongo_client()
        job = db.videos.find_one({"job_id": job_id})
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Remove MongoDB ObjectId for JSON serialization
        job.pop("_id", None)
        
        return job
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs")
async def list_jobs(limit: int = 10, skip: int = 0):
    """List recent conversion jobs."""
    try:
        db = get_mongo_client()
        jobs = list(db.videos.find().sort("created_at", -1).skip(skip).limit(limit))
        
        # Remove ObjectId
        for job in jobs:
            job.pop("_id", None)
        
        return {"jobs": jobs, "total": db.videos.count_documents({})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

