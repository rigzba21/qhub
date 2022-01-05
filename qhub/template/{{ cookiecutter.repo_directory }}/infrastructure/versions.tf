terraform {
  required_providers {
{%- if cookiecutter.provider == "aws" %}
    aws = {
      source = "hashicorp/aws"
      version = "3.64.2"
    }
{%- elif cookiecutter.provider == "azure" %}
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "=2.44.0"
    }
{%- elif cookiecutter.provider == "gcp" %}
    google = {
      source = "hashicorp/google"
      version = "=3.89.0"
    }
{%- elif cookiecutter.provider == "do" %}
    digitalocean = {
      source = "digitalocean/digitalocean"
      version = "=2.14.0"
    }
{% endif %}
    helm = {
      source  = "hashicorp/helm"
      version = "2.1.2"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.4"
    }
    keycloak = {
      source  = "mrparkers/keycloak"
      version = "3.3.0"
    }
  }
  required_version = ">= 0.13"
}
