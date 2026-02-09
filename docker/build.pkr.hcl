packer {
  required_plugins {
    docker = {
      version = ">= 1.0.0"
      source  = "github.com/hashicorp/docker"
    }
  }
}

variable "image_repository" {
  type = string
}

variable "image_tag" {
  type = string
  default = "latest"
}

source "docker" "ytbackup" {
  image  = "public.ecr.aws/docker/library/python:3.12-slim"
  commit = true
  changes = [
    "WORKDIR /app",
    "EXPOSE 8080",
    "CMD [\"python\", \"app.py\"]",
    "ENV PORT 8080",
    "ENV TZ=America/New_York"
  ]
}

build {
  name = "ytbackup"
  sources = ["source.docker.ytbackup"]

  # Install system dependencies
  provisioner "shell" {
    inline = [
      "apt-get update && apt-get install -y ffmpeg curl unzip ca-certificates",
      "rm -rf /var/lib/apt/lists/*",
      "mkdir -p /app"
    ]
  }

  # Install Deno (JavaScript runtime required by yt-dlp for YouTube extraction)
  provisioner "shell" {
    inline = [
      "curl -fsSL https://deno.land/install.sh | sh",
      "mv /root/.deno/bin/deno /usr/local/bin/deno",
      "deno --version"
    ]
  }

  # Enable yt-dlp remote components for JS challenge solving
  # This creates the config directory and sets up the environment
  provisioner "shell" {
    inline = [
      "mkdir -p /root/.config/yt-dlp",
      "echo '--remote-components ejs:github' > /root/.config/yt-dlp/config"
    ]
  }

  # Install AWS CLI
  provisioner "shell" {
    inline = [
      "curl \"https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip\" -o \"/awscliv2.zip\"",
      "unzip /awscliv2.zip -d /",
      "/aws/install",
      "rm -rf /awscliv2.zip /aws",
      "aws --version"
    ]
  }

  # Copy and install requirements
  provisioner "file" {
    source      = "../app/requirements.txt"
    destination = "/app/requirements.txt"
  }

  provisioner "shell" {
    inline = [
      "pip install --no-cache-dir -r /app/requirements.txt",
      "yt-dlp --version"
    ]
  }

  # Copy application code
  provisioner "file" {
    source      = "../app/app.py"
    destination = "/app/app.py"
  }

  # Create directories
  provisioner "shell" {
    inline = [
      "mkdir -p /tmp/yt-downloads /.config"
    ]
  }

  post-processors {
    post-processor "docker-tag" {
      repository = var.image_repository
      tags       = [var.image_tag, "latest"]
    }
    post-processor "docker-push" {
        ecr_login = true
        login_server = split("/", var.image_repository)[0]
    }
  }
}
