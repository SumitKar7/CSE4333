FROM python:3.11-slim

# Install FFmpeg (required for video conversion)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install dependencies
COPY services/converter_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create app directory structure
RUN mkdir -p app

# Copy converter module (built from project root context)
COPY app/converter.py ./app/converter.py
COPY app/__init__.py ./app/__init__.py

# Copy worker script
COPY services/converter_service/worker.py .

# Create output directory
RUN mkdir -p /tmp/outputs

CMD ["python", "worker.py"]

