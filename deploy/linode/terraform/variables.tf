variable "linode_token" {
  description = "Linode personal access token (set via LINODE_TOKEN env var)"
  type        = string
  sensitive   = true
}

variable "region" {
  description = "Linode region for all resources"
  type        = string
  default     = "us-east"
}

variable "domain" {
  description = "Preview domain (e.g. state-preview.akamai.ai)"
  type        = string
  default     = "state-preview.akamai.ai"
}

variable "ssh_key" {
  description = "SSH public key for Linode root access"
  type        = string
  default     = ""
}

variable "db_password" {
  description = "PostgreSQL admin password"
  type        = string
  sensitive   = true
  default     = "changeme-in-production"
}

variable "obj_access_key" {
  description = "Object Storage access key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "obj_secret_key" {
  description = "Object Storage secret key"
  type        = string
  sensitive   = true
  default     = ""
}
