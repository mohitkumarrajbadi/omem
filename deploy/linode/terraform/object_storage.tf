# Object Storage — snapshot archives, audit exports, large memory exports

resource "linode_object_storage_bucket" "snapshots" {
  cluster = "${var.region}-1"   # e.g. us-east-1
  label   = "omem-preview-snapshots"
  acl     = "private"

  lifecycle_rule {
    id      = "expire-old-snapshots"
    enabled = true

    expiration {
      days = 30   # Preview tier — keep for 30 days only
    }
  }
}

resource "linode_object_storage_key" "omem_service" {
  label = "omem-preview-service-key"

  bucket_access {
    bucket_name = linode_object_storage_bucket.snapshots.label
    cluster     = linode_object_storage_bucket.snapshots.cluster
    permissions = "read_write"
  }
}

output "obj_bucket" {
  value = linode_object_storage_bucket.snapshots.label
}

output "obj_endpoint" {
  value = "https://${linode_object_storage_bucket.snapshots.cluster}.linodeobjects.com"
}

output "obj_access_key" {
  value     = linode_object_storage_key.omem_service.access_key
  sensitive = true
}

output "obj_secret_key" {
  value     = linode_object_storage_key.omem_service.secret_key
  sensitive = true
}
