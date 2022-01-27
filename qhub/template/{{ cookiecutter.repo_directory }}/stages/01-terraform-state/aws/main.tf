variable "name" {
  description = "Prefix name to assign to QHub resources"
  type        = string
}

variable "namespace" {
  description = "Namespace to create Kubernetes resources"
  type        = string
}

module "terraform-state" {
  source = "../modules/aws/terraform-state"

  name = "${var.project_name }-${var.namespace}"

  tags = {
    Project     = var.name
    Owner       = "terraform-state"
    Environment = var.namespace
  }
}

terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
      version = "3.73.0"
    }
  }
  required_version = ">= 1.0"
}