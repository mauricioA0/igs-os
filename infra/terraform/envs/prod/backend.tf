# State lives in the bucket created by ../../bootstrap. Init with:
#   terraform init -backend-config="bucket=<project_id>-tfstate"
terraform {
  backend "gcs" {
    prefix = "igs-os/prod"
  }
}
