resource "aws_ecr_repository" "yt_backup" {
  name                 = "yt-backup"
  image_tag_mutability = "MUTABLE"
}

resource "aws_ecr_lifecycle_policy" "yt_backup" {
  repository = aws_ecr_repository.yt_backup.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = {
        type = "expire"
      }
    }]
  })
}

output "repository_url" {
  value = aws_ecr_repository.yt_backup.repository_url
}
