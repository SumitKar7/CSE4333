# Video to Audio Converter

A cloud-native microservices application that converts video files to MP3 audio files using FFmpeg. Upload a video, and the system will automatically extract and convert the audio for you.

## 🚀 Quick Start

### Prerequisites

- **Docker** and **Docker Compose** installed on your machine
- That's it! Everything else runs in containers.

### Running the Application

1. **Clone or navigate to the project:**
   ```bash
   cd video-to-audio
   ```

2. **Start all services:**
   ```bash
   docker compose up -d
   ```

3. **Wait for services to start** (about 30 seconds):
   ```bash
   docker compose ps
   ```
   All services should show as "Up" and healthy.

4. **Open your web browser** and go to:
   ```
   http://localhost:8000
   ```

5. **Upload and convert:**
   - Click the upload area or drag & drop a video file
   - Click "Upload & Convert"
   - Wait for processing (you'll see real-time status updates)
   - When complete, click the "Download MP3" button

That's it! Your video is now converted to audio. 🎉

## 📱 Using the Web Interface

### Step-by-Step Guide

1. **Open the application:**
   - Go to http://localhost:8000 in your web browser

2. **Upload a video:**
   - Click the upload area, OR
   - Drag and drop a video file onto the upload area
   - Supported formats: MP4, AVI, MOV, and other video formats

3. **Monitor progress:**
   - **Queued**: Your video is waiting in the queue
   - **Processing**: Converting video to audio (this may take a few seconds to minutes depending on file size)
   - **Completed**: Your audio file is ready!
   - **Failed**: Something went wrong (you'll see an error message)

4. **Download your audio:**
   - When status shows "Completed", click the green "Download MP3" button
   - The file will download to your computer

### Features

- ✨ **Beautiful modern UI** with drag-and-drop support
- 📊 **Real-time status updates** as your video processes
- 🎯 **Progress indicators** so you know what's happening
- ⚡ **Fast processing** using FFmpeg
- 📱 **Works on mobile** and desktop browsers

## 🛠️ Using Command Line (Advanced)

If you prefer using command line tools:

### Upload a video:
```bash
curl -X POST "http://localhost:8000/upload" \
  -F "file=@your-video.mp4;type=video/mp4" \
  -F "user_id=your-name"
```

You'll get a response with a `job_id`.

### Check job status:
```bash
curl "http://localhost:8000/job/{job_id}"
```

### Download converted audio:
```bash
curl "http://localhost:8001/download/{job_id}" -o output.mp3
```

## 🏗️ Architecture

The application consists of three microservices:

1. **Upload Service** - Receives video uploads and queues them for processing
2. **Converter Service** - Processes videos and extracts audio
3. **Storage Service** - Provides download endpoints for converted files

**Technology Stack:**
- Python (FastAPI) for REST APIs
- RabbitMQ for job queuing
- MongoDB Atlas for metadata storage
- PostgreSQL for logging
- FFmpeg for video/audio conversion

## 📍 Service URLs

- **Web Interface**: http://localhost:8000
- **Upload Service API**: http://localhost:8000
- **Storage Service API**: http://localhost:8001
- **RabbitMQ Management**: http://localhost:15672 (username: `guest`, password: `guest`)

## 🔧 Management Commands

### View logs:
```bash
docker compose logs -f
```

### View logs for specific service:
```bash
docker compose logs -f upload-service
docker compose logs -f converter-service
docker compose logs -f storage-service
```

### Stop all services:
```bash
docker compose down
```

### Restart services:
```bash
docker compose restart
```

### Check service status:
```bash
docker compose ps
```

## 🐛 Troubleshooting

### Services won't start?
- Make sure Docker is running
- Check if ports 8000, 8001, 15672 are available
- View logs: `docker compose logs`

### Can't upload files?
- Make sure you're selecting a video file (MP4, AVI, MOV, etc.)
- Check file size (very large files may take longer)
- View upload service logs: `docker compose logs upload-service`

### Download not working?
- Wait for conversion to complete (status should be "completed")
- Check the job status: `curl "http://localhost:8000/job/{job_id}"`
- View storage service logs: `docker compose logs storage-service`

### MongoDB connection issues?
- Make sure your MongoDB Atlas cluster has network access configured
- Check that IP `0.0.0.0/0` is whitelisted in MongoDB Atlas Network Access

## 📝 API Endpoints

### Upload Service (Port 8000)

- `GET /` - Web interface
- `POST /upload` - Upload video file
- `GET /job/{job_id}` - Get job status
- `GET /jobs` - List recent jobs
- `GET /health` - Health check

### Storage Service (Port 8001)

- `GET /download/{job_id}` - Download converted audio file
- `GET /job/{job_id}/info` - Get job information
- `GET /health` - Health check

## 🎯 What's Next?

This project is ready for:
- Kubernetes deployment (AWS EKS)
- CI/CD pipeline setup
- Monitoring with Prometheus & Grafana
- Production deployment

## 👥 Team

- **Sumit Karki** - AWS EKS setup, Kubernetes deployments
- **Bhuwan Upadhyaya** - Microservice development, Dockerization
- **Yukesh Shrestha** - Database setup, CI/CD, Monitoring

## 📄 License

This project is created for academic purposes.
