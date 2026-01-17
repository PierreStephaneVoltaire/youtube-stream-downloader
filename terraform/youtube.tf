# DynamoDB Table: youtube-live-notifications
resource "aws_dynamodb_table" "youtube_live_notifications" {
  name         = "youtube-live-notifications"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "videoId"

  attribute {
    name = "videoId"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Name        = "youtube-live-notifications"
    Environment = var.environment
    Purpose     = "YouTube live stream notifications tracking"
  }
}

# DynamoDB Table: youtube-channel-cache
resource "aws_dynamodb_table" "youtube_channel_cache" {
  name         = "youtube-channel-cache"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "handle"

  attribute {
    name = "handle"
    type = "S"
  }

  attribute {
    name = "channelId"
    type = "S"
  }

  global_secondary_index {
    name            = "channelId-index"
    hash_key        = "channelId"
    projection_type = "ALL"
  }

  tags = {
    Name        = "youtube-channel-cache"
    Environment = var.environment
    Purpose     = "YouTube channel metadata cache"
  }
}

# S3 Bucket for YouTube video backups
resource "aws_s3_bucket" "youtube_backup" {
  bucket = "${var.project_name}-youtube-backup-${var.environment}"

  tags = {
    Name        = "${var.project_name}-youtube-backup"
    Environment = var.environment
    Purpose     = "YouTube video backup storage"
  }
}

# Enable versioning for backup bucket
resource "aws_s3_bucket_versioning" "youtube_backup" {
  bucket = aws_s3_bucket.youtube_backup.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption for backup bucket
resource "aws_s3_bucket_server_side_encryption_configuration" "youtube_backup" {
  bucket = aws_s3_bucket.youtube_backup.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access to backup bucket
resource "aws_s3_bucket_public_access_block" "youtube_backup" {
  bucket = aws_s3_bucket.youtube_backup.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle rule: Move to Standard-IA after 30 days
resource "aws_s3_bucket_lifecycle_configuration" "youtube_backup" {
  bucket = aws_s3_bucket.youtube_backup.id

  rule {
    id     = "move-to-ia-30-days"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
  }
}

# SSM Parameter for YouTube cookies
resource "aws_ssm_parameter" "youtube_cookies" {
  name        = var.cookies_parameter_name
  description = "YouTube cookies for authenticated video downloads"
  type        = "SecureString"
  tier        = "Advanced"
  value       = "# Placeholder - Update with actual cookies from browser export"

  lifecycle {
    ignore_changes = [value]
  }

  tags = {
    Name        = "youtube-cookies"
    Environment = var.environment
  }
}
