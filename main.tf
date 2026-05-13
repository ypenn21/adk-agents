# 1. The Workload Identity Pool and Provider
module "gh_oidc" {
  source      = "terraform-google-modules/github-actions-runners/google//modules/gh-oidc"
  project_id  = "genai-apps-25"
  pool_id     = "aaa-github-pool"
  provider_id = "github-provider"
  
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.owner"      = "assertion.repository_owner"
  }

  # HARDCODE YOUR ORG HERE - This protects your project from other GitHub users
  attribute_condition = "assertion.repository_owner == 'cloud-gtm-core-apps' || assertion.repository_owner == 'ypenn21'"
}

# 2. Enable Required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com"
  ])
  project = "genai-apps-25"
  service = each.key

  disable_on_destroy = false
}

# 3. The IAM Binding (The "Permissions" link)
resource "google_service_account_iam_member" "wif_binding" {
  # Your specific service account
  service_account_id = "projects/genai-apps-25/serviceAccounts/803095609412-compute@developer.gserviceaccount.com"
  role               = "roles/iam.workloadIdentityUser"
  
  # Locked specifically to your repository
  member = "principalSet://iam.googleapis.com/projects/803095609412/locations/global/workloadIdentityPools/aaa-github-pool/attribute.repository/cloud-gtm-core-apps/e2e-agent-patterns"
}

resource "google_service_account_iam_member" "wif_binding_adk" {
  service_account_id = "projects/genai-apps-25/serviceAccounts/803095609412-compute@developer.gserviceaccount.com"
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/projects/803095609412/locations/global/workloadIdentityPools/aaa-github-pool/attribute.repository/ypenn21/adk-agents"
}

# 4. GCS Bucket for Scan Reports
resource "google_storage_bucket" "scan_reports" {
  name     = "genai-apps-25-scan-reports"
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
  project = "genai-apps-25"
  role    = each.key
  member  = "serviceAccount:803095609412-compute@developer.gserviceaccount.com"
}
