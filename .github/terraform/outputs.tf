output "workload_identity_provider" {
  description = "The Workload Identity Provider resource identifier for GitHub Actions authentication"
  value       = "projects/${var.project_number}/locations/global/workloadIdentityPools/${var.pool_id}/providers/${var.provider_id}"
}

output "service_account_email" {
  description = "The service account email assumed by the GitHub workflow"
  value       = var.service_account_email
}

output "scan_reports_bucket" {
  description = "The Cloud Storage bucket created for storing audit and scan reports"
  value       = google_storage_bucket.scan_reports.name
}
