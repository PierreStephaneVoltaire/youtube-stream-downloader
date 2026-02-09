resource "kubernetes_namespace" "yt_backup" {
  metadata {
    name = "yt-backup"
  }
}

resource "kubernetes_secret" "yt_backup_creds" {
  metadata {
    name      = "yt-backup-creds"
    namespace = kubernetes_namespace.yt_backup.metadata[0].name
  }

  data = {
    AWS_ACCESS_KEY_ID     = var.aws_access_key
    AWS_SECRET_ACCESS_KEY = var.aws_secret_key
  }

  type = "Opaque"
}

resource "kubernetes_secret" "yt_cookies" {
  metadata {
    name      = "yt-cookies"
    namespace = kubernetes_namespace.yt_backup.metadata[0].name
  }

  data = {
    "cookies.txt" = file(var.cookies_file_path)
  }

  type = "Opaque"
}

data "aws_ecr_authorization_token" "token" {}

resource "kubernetes_secret" "ecr_registry" {
  metadata {
    name      = "ecr-registry"
    namespace = kubernetes_namespace.yt_backup.metadata[0].name
  }

  type = "kubernetes.io/dockerconfigjson"

  data = {
    ".dockerconfigjson" = jsonencode({
      auths = {
        "${data.aws_ecr_authorization_token.token.proxy_endpoint}" = {
          auth = data.aws_ecr_authorization_token.token.authorization_token
        }
      }
    })
  }
}

resource "kubernetes_persistent_volume_claim" "yt_backup_pvc" {
  metadata {
    name      = "yt-backup-pvc"
    namespace = kubernetes_namespace.yt_backup.metadata[0].name
  }

  spec {
    access_modes = ["ReadWriteOnce"]
    resources {
      requests = {
        storage = "10Gi"
      }
    }
    storage_class_name = "do-block-storage"
  }
  
  wait_until_bound = false
  depends_on = [null_resource.packer_build]

}

resource "kubernetes_deployment" "yt_backup" {
  metadata {
    name      = "yt-backup"
    namespace = kubernetes_namespace.yt_backup.metadata[0].name
    labels = {
      app = "yt-backup"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "yt-backup"
      }
    }

    template {
      metadata {
        labels = {
          app = "yt-backup"
        }
      }
     

      spec {
           node_selector = {
          "workload-type" = "general"
        }
        
        toleration {
          key      = "dedicated"
          operator = "Equal"
          value    = "general"
          effect   = "NoSchedule"
        }

        image_pull_secrets {
          name = kubernetes_secret.ecr_registry.metadata[0].name
        }

        container {
          image = "${aws_ecr_repository.yt_backup.repository_url}:latest"
          name  = "yt-backup"

          port {
            container_port = 8080
          }

          env {
            name  = "PORT"
            value = "8080"
          }
          env {
            name  = "DOWNLOAD_DIR"
            value = "/tmp/yt-downloads"
          }
          env {
            name  = "COOKIES_FILE"
            value = "/.config/cookies.txt"
          }
          env {
            name  = "AWS_DEFAULT_REGION"
            value = var.region
          }
          env {
            name  = "COOKIES_PARAMETER"
            value = var.cookies_parameter_name
          }

          volume_mount {
            name       = "cookies"
            mount_path = "/.config"
            read_only  = true
          }
          env {
            name  = "BACKUP_BUCKET"
            value = aws_s3_bucket.youtube_backup.bucket
          }
          env {
            name  = "TZ"
            value = "America/New_York"
          }
          env {
            name = "AWS_ACCESS_KEY_ID"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.yt_backup_creds.metadata[0].name
                key  = "AWS_ACCESS_KEY_ID"
              }
            }
          }
          env {
            name = "AWS_SECRET_ACCESS_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.yt_backup_creds.metadata[0].name
                key  = "AWS_SECRET_ACCESS_KEY"
              }
            }
          }

          volume_mount {
            name       = "download-storage"
            mount_path = "/tmp/yt-downloads"
          }

          resources {
            requests = {
              memory = "128Mi"
            }
            limits = {
              memory = "1Gi"
            }
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8080
            }
            initial_delay_seconds = 30
            period_seconds        = 10
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8080
            }
            initial_delay_seconds = 10
            period_seconds        = 5
          }
        }

        volume {
          name = "download-storage"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.yt_backup_pvc.metadata[0].name
          }
        }

        volume {
          name = "cookies"
          secret {
            secret_name = kubernetes_secret.yt_cookies.metadata[0].name
            items {
              key  = "cookies.txt"
              path = "cookies.txt"
            }
          }
        }
      }
    }
  }

  depends_on = [null_resource.packer_build]
}

resource "kubernetes_service" "yt_backup" {
  metadata {
    name      = "yt-backup"
    namespace = kubernetes_namespace.yt_backup.metadata[0].name
  }

  spec {
    selector = {
      app = "yt-backup"
    }

    port {
      port        = 8080
      target_port = 8080
    }

    type = "ClusterIP"
  }
}

resource "kubernetes_ingress_v1" "yt_backup" {
  metadata {
    name      = "yt-backup"
    namespace = kubernetes_namespace.yt_backup.metadata[0].name
  }

  spec {
    rule {
      host = "yt-backup.local"
      http {
        path {
          path      = "/"
          path_type = "Prefix"
          backend {
            service {
              name = kubernetes_service.yt_backup.metadata[0].name
              port {
                number = 8080
              }
            }
          }
        }
      }
    }
  }
}
