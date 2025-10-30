"""
Converter Service - Worker that consumes jobs from RabbitMQ
and converts video files to audio using FFmpeg.
"""

import os
import json
import pika
from pathlib import Path
from pymongo import MongoClient
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import sys
import time
from pika import exceptions as pika_exceptions

# Add app directory to path to import converter
sys.path.insert(0, str(Path(__file__).parent / "app"))
from converter import convert_to_audio, ConversionError

# Configuration
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

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/outputs"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_mongo_client():
    """Get MongoDB database client."""
    client = MongoClient(MONGODB_URI)
    return client[MONGODB_DB]


def get_postgres_conn():
    """Get PostgreSQL connection."""
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )


def process_video(job_id: str, file_path: str, original_filename: str):
    """
    Process a video file: convert to audio and update databases.
    
    Args:
        job_id: Unique job identifier
        file_path: Path to input video file
        original_filename: Original filename for reference
    """
    db = get_mongo_client()
    
    try:
        # Update status to processing
        db.videos.update_one(
            {"job_id": job_id},
            {"$set": {"status": "processing", "updated_at": datetime.utcnow().isoformat()}}
        )
        
        # Update PostgreSQL
        conn = get_postgres_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE conversion_jobs
            SET status = 'processing'
            WHERE job_id = %s
        """, (job_id,))
        conn.commit()
        
        # Log processing start
        cur.execute("""
            INSERT INTO request_logs (job_id, action, details)
            VALUES (%s, %s, %s)
        """, (job_id, "processing_started", json.dumps({
            "file_path": file_path,
            "timestamp": datetime.utcnow().isoformat()
        })))
        conn.commit()
        cur.close()
        
        # Check if input file exists
        input_path = Path(file_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")
        
        # Generate output audio file path
        output_filename = f"{job_id}.mp3"
        output_path = OUTPUT_DIR / output_filename
        
        # Convert video to audio
        print(f"Converting {file_path} to {output_path}...")
        return_code, result_path = convert_to_audio(
            str(input_path),
            str(output_path),
            codec="mp3",
            quality=2
        )
        
        if return_code != 0:
            raise ConversionError(f"FFmpeg returned non-zero exit code: {return_code}")
        
        # Get output file size
        output_size = Path(result_path).stat().st_size
        
        # Update MongoDB with success
        db.videos.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "completed",
                "audio_file_path": str(output_path),
                "audio_file_size": output_size,
                "updated_at": datetime.utcnow().isoformat(),
                "completed_at": datetime.utcnow().isoformat()
            }}
        )
        
        # Update PostgreSQL
        conn = get_postgres_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE conversion_jobs
            SET status = 'completed',
                audio_file_path = %s,
                completed_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
        """, (str(output_path), job_id))
        conn.commit()
        
        # Log completion
        cur.execute("""
            INSERT INTO request_logs (job_id, action, details)
            VALUES (%s, %s, %s)
        """, (job_id, "processing_completed", json.dumps({
            "audio_file_path": str(output_path),
            "audio_file_size": output_size,
            "timestamp": datetime.utcnow().isoformat()
        })))
        conn.commit()
        cur.close()
        
        print(f"✓ Job {job_id} completed successfully. Audio saved to {output_path}")
        
    except ConversionError as e:
        error_msg = str(e)
        print(f"✗ Conversion error for job {job_id}: {error_msg}")
        
        # Update MongoDB with error
        db.videos.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "failed",
                "error": error_msg,
                "updated_at": datetime.utcnow().isoformat()
            }}
        )
        
        # Update PostgreSQL
        conn = get_postgres_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE conversion_jobs
            SET status = 'failed'
            WHERE job_id = %s
        """, (job_id,))
        conn.commit()
        
        cur.execute("""
            INSERT INTO request_logs (job_id, action, details)
            VALUES (%s, %s, %s)
        """, (job_id, "processing_failed", json.dumps({
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat()
        })))
        conn.commit()
        cur.close()
        
    except Exception as e:
        error_msg = str(e)
        print(f"✗ Unexpected error for job {job_id}: {error_msg}")
        
        # Update databases with error
        db.videos.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "failed",
                "error": error_msg,
                "updated_at": datetime.utcnow().isoformat()
            }}
        )
        
        conn = get_postgres_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE conversion_jobs
            SET status = 'failed'
            WHERE job_id = %s
        """, (job_id,))
        conn.commit()
        cur.close()


def callback(ch, method, properties, body):
    """
    RabbitMQ callback function that processes incoming messages.
    """
    try:
        message = json.loads(body.decode('utf-8'))
        job_id = message.get("job_id")
        file_path = message.get("file_path")
        original_filename = message.get("original_filename", "unknown")
        
        print(f"Received job: {job_id} for file: {file_path}")
        
        # Process the video
        process_video(job_id, file_path, original_filename)
        
        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except json.JSONDecodeError as e:
        print(f"Error decoding message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        print(f"Error processing message: {e}")
        # Reject and requeue the message
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def start_consumer():
    """Create a connection and start consuming messages (single session)."""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=300,
        connection_attempts=5,
        retry_delay=5,
    )

    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    # Declare queue as durable
    channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)

    # Process one message at a time
    channel.basic_qos(prefetch_count=1)

    # Set up consumer
    channel.basic_consume(
        queue=RABBITMQ_QUEUE,
        on_message_callback=callback
    )

    print(f"Waiting for messages in queue '{RABBITMQ_QUEUE}'. To exit press CTRL+C")
    channel.start_consuming()


def main():
    """Main loop that auto-reconnects to RabbitMQ on failures with backoff."""
    print("Starting Converter Worker...")
    backoff_seconds = 2
    max_backoff = 30

    while True:
        try:
            print(f"Connecting to RabbitMQ at {RABBITMQ_HOST}:{RABBITMQ_PORT}")
            start_consumer()
            # If start_consumer returns, it likely stopped gracefully
            backoff_seconds = 2  # reset after a successful session
        except KeyboardInterrupt:
            print("\nShutting down worker...")
            break
        except (pika_exceptions.AMQPConnectionError, pika_exceptions.StreamLostError, pika_exceptions.AMQPChannelError) as e:
            print(f"RabbitMQ connection lost: {e}. Retrying in {backoff_seconds}s...")
            time.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, max_backoff)
            continue
        except Exception as e:
            print(f"Unexpected error in worker: {e}. Retrying in {backoff_seconds}s...")
            time.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, max_backoff)
            continue


if __name__ == "__main__":
    main()

