#!/usr/bin/env python3
"""
Local API for downloading YouTube videos (including livestreams/membership content)
and uploading to S3.
"""

import os
import subprocess
import logging
import threading
import uuid
import json
import re
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import boto3
from botocore.exceptions import ClientError

app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
COOKIES_FILE = os.environ.get('COOKIES_FILE', os.path.expanduser('./.config/cookies.txt'))
DOWNLOAD_DIR = os.environ.get('DOWNLOAD_DIR', '/tmp/yt-downloads')
AWS_PROFILE = os.environ.get('AWS_PROFILE', None)
AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'ca-central-1')
COOKIES_PARAMETER = os.environ.get('COOKIES_PARAMETER')
BACKUP_BUCKET = os.environ.get('BACKUP_BUCKET')

# Track job status
jobs = {}

# Ensure download dir exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def download_cookies_from_ssm():
    """Download YouTube cookies from AWS SSM Parameter Store."""
    try:
        logger.info(f"Downloading cookies from Parameter Store: {COOKIES_PARAMETER}")

        ssm = boto3.client('ssm', region_name=AWS_REGION)
        response = ssm.get_parameter(
            Name=COOKIES_PARAMETER,
            WithDecryption=True
        )

        cookies_content = response['Parameter']['Value']

        # Ensure directory exists
        cookies_dir = os.path.dirname(COOKIES_FILE)
        os.makedirs(cookies_dir, exist_ok=True)

        # Write cookies to file
        with open(COOKIES_FILE, 'w') as f:
            f.write(cookies_content)

        logger.info(f"Cookies downloaded successfully to {COOKIES_FILE}")
        return True

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ParameterNotFound':
            logger.warning(f"Cookies parameter not found: {COOKIES_PARAMETER}")
            logger.warning("Will attempt to use existing cookies file if available")
        else:
            logger.error(f"Error downloading cookies from Parameter Store: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error downloading cookies: {e}")
        return False


# Download cookies at startup
download_cookies_from_ssm()


def download_video(video_url: str, video_id: str, output_dir: str) -> str:
    """Download video using yt-dlp with browser cookies."""

    output_template = os.path.join(output_dir, f'{video_id}.%(ext)s')

    cmd = [
        'yt-dlp',
        '--cookies', COOKIES_FILE,
        '--output', output_template,
        # Best quality: best video + best audio, merge with ffmpeg
        '-f', 'bestvideo+bestaudio/best',
        '--merge-output-format', 'mkv',
        # For live streams: download from the start
        '--live-from-start',
        '--no-playlist',
        # Verbose progress
        '--newline',
        '--progress',
        video_url
    ]

    logger.info(f"Running: {' '.join(cmd)}")

    # Stream output in real-time
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # Print output as it comes
    for line in process.stdout:
        line = line.strip()
        if line:
            logger.info(f"[yt-dlp] {line}")

    process.wait()

    if process.returncode != 0:
        raise Exception(f"yt-dlp failed with return code {process.returncode}")

    # Find the output file
    for ext in ['mkv', 'mp4', 'webm']:
        filepath = os.path.join(output_dir, f'{video_id}.{ext}')
        if os.path.exists(filepath):
            logger.info(f"Downloaded to: {filepath}")
            return filepath

    raise Exception("Could not find downloaded file")


def upload_to_s3(local_path: str, bucket: str, video_id: str) -> str:
    """Upload file to S3 bucket."""

    filename = os.path.basename(local_path)
    s3_key = f"{video_id}/{filename}"
    s3_uri = f"s3://{bucket}/{s3_key}"

    cmd = ['aws', 's3', 'cp', local_path, s3_uri]

    if AWS_PROFILE:
        cmd.extend(['--profile', AWS_PROFILE])

    logger.info(f"Uploading to: {s3_uri}")

    # Stream output in real-time
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in process.stdout:
        line = line.strip()
        if line:
            logger.info(f"[s3] {line}")

    process.wait()

    if process.returncode != 0:
        raise Exception(f"S3 upload failed with return code {process.returncode}")

    logger.info(f"Upload complete: {s3_uri}")
    return s3_uri


def process_download(job_id: str, item: dict):
    """Background worker to download and upload."""

    video_id = item.get('videoId')
    video_url = item.get('videoUrl')
    bucket = item.get('bucket')
    title = item.get('title', 'Unknown')

    jobs[job_id]['status'] = 'downloading'
    jobs[job_id]['started_at'] = datetime.now().isoformat()

    logger.info(f"[Job {job_id}] Starting: {title} ({video_id})")

    try:
        # Create directory for this download
        output_dir = os.path.join(DOWNLOAD_DIR, video_id)
        os.makedirs(output_dir, exist_ok=True)

        # Download
        jobs[job_id]['status'] = 'downloading'
        local_path = download_video(video_url, video_id, output_dir)

        # Upload to S3
        jobs[job_id]['status'] = 'uploading'
        s3_uri = upload_to_s3(local_path, bucket, video_id)

        # Cleanup local file
        logger.info(f"[Job {job_id}] Cleaning up local file")
        os.remove(local_path)
        os.rmdir(output_dir)

        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['s3_uri'] = s3_uri
        jobs[job_id]['completed_at'] = datetime.now().isoformat()
        logger.info(f"[Job {job_id}] Completed: {s3_uri}")

    except Exception as e:
        logger.error(f"[Job {job_id}] Failed: {e}")
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)
        jobs[job_id]['failed_at'] = datetime.now().isoformat()


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/download', methods=['POST'])
def download():
    """
    Start download job(s) - returns immediately with job ID(s).

    Expected JSON body (single item or array):
    {
        "videoId": "TFA0RKwkuwI",
        "videoUrl": "https://youtube.com/watch?v=TFA0RKwkuwI",
        "channelTitle": "...",
        "title": "...",
        "bucket": "oshi-backup-26"
    }
    """

    data = request.get_json()

    if not data:
        return jsonify({'error': 'No JSON body provided'}), 400

    # Handle both single item and array
    items = data if isinstance(data, list) else [data]

    results = []

    for item in items:
        video_id = item.get('videoId')
        video_url = item.get('videoUrl')
        bucket = item.get('bucket', BACKUP_BUCKET)
        title = item.get('title', 'Unknown')

        if not all([video_id, video_url, bucket]):
            results.append({
                'videoId': video_id,
                'success': False,
                'error': 'Missing required fields: videoId, videoUrl (and BACKUP_BUCKET not set)'
            })
            continue

        # Create job
        job_id = f"{video_id}-{uuid.uuid4().hex[:8]}"
        jobs[job_id] = {
            'job_id': job_id,
            'video_id': video_id,
            'title': title,
            'status': 'queued',
            'created_at': datetime.now().isoformat()
        }

        # Start background thread
        thread = threading.Thread(
            target=process_download,
            args=(job_id, item),
            daemon=True
        )
        thread.start()

        logger.info(f"[Job {job_id}] Queued: {title}")

        results.append({
            'job_id': job_id,
            'video_id': video_id,
            'title': title,
            'status': 'queued'
        })

    # Return single result if single input, array otherwise
    if not isinstance(data, list):
        return jsonify(results[0])

    return jsonify(results)


@app.route('/status/<job_id>', methods=['GET'])
def job_status(job_id):
    """Get status of a specific job."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(jobs[job_id])


@app.route('/jobs', methods=['GET'])
def list_jobs():
    """List all jobs."""
    return jsonify(list(jobs.values()))


@app.route('/check-live', methods=['GET'])
def check_live():
    """Check if a YouTube channel is live."""
    channel = request.args.get('channel')
    if not channel:
        return jsonify({'error': 'Missing channel parameter'}), 400

    # Sanitize input: allow only alphanumeric, @, _, -
    if not re.match(r'^[a-zA-Z0-9@_-]+$', channel):
        return jsonify({'error': 'Invalid channel format'}), 400

    cmd = [
        'yt-dlp',
        '--cookies', COOKIES_FILE,
        '--dump-json',
        '--skip-download',
        '--no-playlist',
        '--socket-timeout', '10',
        f'https://www.youtube.com/{channel}/live'
    ]

    checked_at = datetime.now().isoformat()

    try:
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15
        )

        stderr = process.stderr.lower() if process.stderr else ""

        # Check for specific errors first
        if "join this channel" in stderr or "members-only" in stderr:
            return jsonify({
                "is_live": False,
                "stream": None,
                "error": "members_only_no_access",
                "checked_at": checked_at
            })

        if "sign in" in stderr or "cookie" in stderr:
            return jsonify({
                "is_live": False,
                "stream": None,
                "error": "auth_expired",
                "detail": "Cookies need refresh",
                "checked_at": checked_at
            }), 401

        if "429" in stderr or "too many requests" in stderr:
            return jsonify({
                "is_live": False,
                "stream": None,
                "error": "Rate limited by YouTube",
                "checked_at": checked_at
            }), 429

        if "404" in stderr or "does not exist" in stderr:
            return jsonify({
                "is_live": False,
                "stream": None,
                "error": "Channel not found",
                "checked_at": checked_at
            }), 404

        # Success - Live
        if process.returncode == 0 and process.stdout:
            try:
                data = json.loads(process.stdout)
                if data.get('is_live'):
                    # Parse start time
                    start_ts = data.get('release_timestamp') or data.get('start_time')
                    start_time = None
                    if start_ts:
                        start_time = datetime.fromtimestamp(start_ts).isoformat()

                    return jsonify({
                        "is_live": True,
                        "stream": {
                            "id": data.get("id"),
                            "title": data.get("title"),
                            "description": data.get("description"),
                            "uploader": data.get("uploader"),
                            "uploader_id": data.get("uploader_id"),
                            "view_count": data.get("view_count"),
                            "start_time": start_time,
                            "thumbnail": data.get("thumbnail")
                        },
                        "error": None,
                        "checked_at": checked_at
                    })
            except json.JSONDecodeError:
                logger.error("Failed to parse yt-dlp JSON output")

        # Success - Offline
        # Covers: "not currently live", non-zero exit code (if not caught above),
        # or returncode 0 but is_live=False
        return jsonify({
            "is_live": False,
            "stream": None,
            "error": None,
            "checked_at": checked_at
        })

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout checking live status for {channel}")
        return jsonify({
            "is_live": False,
            "stream": None,
            "error": "Failed to check stream status",
            "detail": "Timeout",
            "checked_at": checked_at
        }), 500

    except Exception as e:
        logger.error(f"Unexpected error checking live status for {channel}: {e}")
        return jsonify({
            "is_live": False,
            "stream": None,
            "error": "Failed to check stream status",
            "detail": str(e),
            "checked_at": checked_at
        }), 500


@app.route('/channel-info', methods=['GET'])
def channel_info():
    """Get channel metadata."""
    channel = request.args.get('channel')
    if not channel:
        return jsonify({'error': 'Missing channel parameter'}), 400

    # Sanitize input: allow only alphanumeric, @, _, -
    if not re.match(r'^[a-zA-Z0-9@_-]+$', channel):
        return jsonify({'error': 'Invalid channel format'}), 400

    # Handle both full URL and handle
    if channel.startswith('@'):
        url = f'https://www.youtube.com/{channel}'
    else:
        # Assume it's a handle without @ or just the name, though yt-dlp is smart
        # best to ensure we form a valid URL or pass it such that yt-dlp understands
        url = f'https://www.youtube.com/@{channel}' if not channel.startswith('http') else channel

    cmd = [
        'yt-dlp',
        '--cookies', COOKIES_FILE,
        '--dump-single-json',
        '--skip-download',
        '--no-playlist',
        '--socket-timeout', '10',
        url
    ]

    try:
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20
        )

        if process.returncode != 0:
            stderr = process.stderr.lower() if process.stderr else ""
            if "404" in stderr or "not found" in stderr:
                return jsonify({'error': 'Channel not found'}), 404
            
            logger.error(f"yt-dlp error getting channel info: {process.stderr}")
            return jsonify({'error': 'Failed to fetch channel info', 'detail': process.stderr}), 500

        try:
            data = json.loads(process.stdout)
            return jsonify(data)
        except json.JSONDecodeError:
             logger.error("Failed to parse yt-dlp JSON output for channel info")
             return jsonify({'error': 'Failed to parse channel info'}), 500

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout getting info for {channel}")
        return jsonify({'error': 'Timeout fetching channel info'}), 500
    except Exception as e:
        logger.error(f"Unexpected error getting channel info for {channel}: {e}")
        return jsonify({'error': 'Internal server error', 'detail': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting server on port {port}")
    logger.info(f"Cookies file: {COOKIES_FILE}")
    logger.info(f"Download directory: {DOWNLOAD_DIR}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
