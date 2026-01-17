# YouTube Backup Service

A local API service designed to download YouTube videos (including livestreams and membership content) and backup them to AWS S3.

## Tech Stack

- **Language:** Python 3
- **Framework:** Flask
- **Core Libraries:** 
  - `yt-dlp` (Video downloading)
  - `boto3` (AWS SDK)
- **Infrastructure:**
  - Docker & Packer (Containerization)
  - Terraform (Infrastructure as Code)

## Features

- **Video Download:** Downloads videos using `yt-dlp` with support for authenticated content via cookies.
- **S3 Upload:** Automatically uploads downloaded content to a specified AWS S3 bucket.
- **Background Processing:** Handles downloads asynchronously with job tracking.
- **Live Check:** Real-time check to see if a specific YouTube channel is live.
- **Cookie Management:** securely retrieves YouTube cookies from AWS SSM Parameter Store.

## API Endpoints

### 1. Health Check
- **Endpoint:** `GET /health`
- **Description:** Returns the service health status.
- **Response:** `{"status": "ok"}`

### 2. Start Download
- **Endpoint:** `POST /download`
- **Description:** Queues a video for download and upload.
- **Body:**
  ```json
  {
      "videoId": "VIDEO_ID",
      "videoUrl": "https://youtube.com/watch?v=VIDEO_ID",
      "title": "Video Title"
  }
  ```
  *Accepts a single object or an array of objects.*

### 3. Job Status
- **Endpoint:** `GET /status/<job_id>`
- **Description:** Get the status of a specific background job.

### 4. List Jobs
- **Endpoint:** `GET /jobs`
- **Description:** Returns a list of all tracked jobs and their statuses.

### 5. Check Live Status
- **Endpoint:** `GET /check-live?channel=@ChannelHandle`
- **Description:** Checks if a YouTube channel is currently live.
- **Response:** JSON object containing `is_live` status and stream details if available.

### 6. Get Channel Info
- **Endpoint:** `GET /channel-info?channel=@ChannelHandle`
- **Description:** Retrieves full metadata for a channel using `yt-dlp`.
- **Response:** JSON object containing channel metadata (as returned by `yt-dlp --dump-single-json`).
