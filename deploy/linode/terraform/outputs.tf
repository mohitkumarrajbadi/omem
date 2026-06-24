output "api_ip" {
  description = "Public IPv4 of the API Linode"
  value       = linode_instance.api.ip_address
}

output "worker_ip" {
  description = "VLAN IPv4 of the Worker Linode"
  value       = "10.0.0.3"
}

output "preview_url" {
  description = "Base URL for the OMem Cloud tech preview"
  value       = "https://${var.domain}"
}

output "health_check_url" {
  description = "Health endpoint"
  value       = "https://${var.domain}/v1/health"
}

output "openapi_url" {
  description = "OpenAPI spec"
  value       = "https://${var.domain}/v1/openapi.json"
}
