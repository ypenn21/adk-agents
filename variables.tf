variable "project_id" {
  description = "The GCP Project ID"
  type        = string
  default     = "genai-apps-25"
}

variable "project_number" {
  description = "The GCP Project Number"
  type        = string
  default     = "803095609412"
}

variable "service_account_email" {
  description = "The service account email to bind to WIF"
  type        = string
  default     = "803095609412-compute@developer.gserviceaccount.com"
}

variable "pool_id" {
  description = "The ID of the Workload Identity Pool"
  type        = string
  default     = "aaa-github-pool"
}

variable "provider_id" {
  description = "The ID of the Workload Identity Provider"
  type        = string
  default     = "github-provider"
}

variable "repository_owners" {
  description = "List of GitHub organizations/users allowed to use this provider"
  type        = list(string)
  default     = ["cloud-gtm-core-apps", "ypenn21"]

  validation {
    condition     = length(var.repository_owners) > 0
    error_message = "At least one repository owner must be specified to prevent insecure access."
  }
}

variable "repositories" {
  description = "List of repositories (org/repo) allowed to assume the service account"
  type        = list(string)
  default     = ["cloud-gtm-core-apps/e2e-agent-patterns", "ypenn21/adk-agents"]
}
