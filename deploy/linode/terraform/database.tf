# DBaaS PostgreSQL — multi-tenant state + memory metadata
# Uses Linode Managed Database (counts as 1 entity).

resource "linode_database_postgresql" "omem_preview" {
  label   = "omem-preview-db"
  region  = var.region
  type    = "g6-nanode-1"   # Smallest DBaaS plan
  engine_id = "postgresql/14"

  cluster_size = 1   # Single node for preview; 3-node HA for production

  encrypted       = true
  ssl_connection  = true
  replication_type = "none"

  allow_list = [
    # API and Worker VLANs access via private network
    # Add Linode instance IPs here after provisioning API/Worker
    # or restrict to VPC/VLAN subnet
    "10.0.0.0/24",
  ]

  # Backups enabled by default on DBaaS — no extra config needed
}

output "db_host" {
  value     = linode_database_postgresql.omem_preview.host_primary
  sensitive = false
}

output "db_url" {
  value = format(
    "postgresql://linpostgres:%s@%s:5432/postgres?sslmode=require",
    var.db_password,
    linode_database_postgresql.omem_preview.host_primary
  )
  sensitive = true
}
