terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "4.35.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "3.4.3"
    }
  }

  backend "local" {}
}

variable "state_prefix" {
  type        = string
  description = "What to prefix to the state bucket to make it slightly more identifiable"
  default     = ""
}
