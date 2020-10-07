terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "3.9.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "2.3.0"
    }
  }

  backend "local" {}
}

variable "state_prefix" {
  type        = string
  description = "What to prefix to the state bucket to make it slightly more identifiable"
  default     = ""
}
