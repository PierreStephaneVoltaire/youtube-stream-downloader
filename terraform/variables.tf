variable "project_name" {
  description = "Project name"
  type        = string
  default     = "personal-ai"
}

variable "environment" {
  description = "Environment (e.g. dev, prod)"
  type        = string
  default     = "dev"
}

variable "region" {
  description = "AWS Region"
  type        = string
  default     = "ca-central-1"
}

variable "cookies_parameter_name" {
  description = "SSM Parameter name for cookies"
  type        = string
  default     = "/personalai/dev/youtube/cookies"
}

variable "aws_access_key" {
  description = "AWS Access Key ID for the application"
  type        = string
  sensitive   = true
}

variable "aws_secret_key" {
  description = "AWS Secret Access Key for the application"
  type        = string
  sensitive   = true
}