# 1. The Workload Identity Pool and Provider
module "gh_oidc" {
  source      = "terraform-google-modules/github-actions-runners/google//modules/gh-oidc"
  project_id  = var.project_id
  pool_id     = var.pool_id
  provider_id = var.provider_id
  
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.owner"      = "assertion.repository_owner"
  }

  # This protects your project from other GitHub users by restricting to specific owners
  attribute_condition = join(" || ", [for owner in var.repository_owners : "assertion.repository_owner == '${owner}'"])
}

# 2. Enable Required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com"
  ])
  project = var.project_id
  service = each.key

  disable_on_destroy = false
}

# 3. The IAM Bindings (The "Permissions" links)
resource "google_service_account_iam_member" "wif_bindings" {
  for_each = toset(var.repositories)

  # Your specific service account
  service_account_id = "projects/${var.project_id}/serviceAccounts/${var.service_account_email}"
  role               = "roles/iam.workloadIdentityUser"
  
  # Locked specifically to your repository
  member = "principalSet://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/${var.pool_id}/attribute.repository/${each.value}"
}

# 4. GCS Bucket for Scan Reports
resource "google_storage_bucket" "scan_reports" {
  name     = "${var.project_id}-scan-reports"
  location = "US"
  force_destroy = true

  uniform_bucket_level_access = true
}

# 5. Project-level IAM for CI/CD Service Account
resource "google_project_iam_member" "cicd_roles" {
  for_each = toset([
    "roles/cloudbuild.builds.editor",
    "roles/artifactregistry.writer",
    "roles/storage.objectAdmin",
    "roles/run.admin",
    "roles/iam.serviceAccountUser"
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${var.service_account_email}"
}
