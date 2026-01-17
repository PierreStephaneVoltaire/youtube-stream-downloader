output "ecr_repository_url" {
  description = "URL of the ECR repository"
  value       = aws_ecr_repository.yt_backup.repository_url
}

output "service_name" {
  description = "Name of the Kubernetes service"
  value       = kubernetes_service.yt_backup.metadata[0].name
}

output "namespace" {
  description = "Kubernetes namespace"
  value       = kubernetes_namespace.yt_backup.metadata[0].name
}

output "backup_bucket_name" {
  description = "Name of the S3 bucket for backups"
  value       = aws_s3_bucket.youtube_backup.bucket
}

output "dynamodb_notifications_table" {
  description = "DynamoDB table for live notifications"
  value       = aws_dynamodb_table.youtube_live_notifications.name
}