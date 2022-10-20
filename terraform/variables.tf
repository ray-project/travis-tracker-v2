terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "4.35.0"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region = "us-west-2"
}

provider "aws" {
  alias = "cloudfront"

  region = "us-east-1"
}

variable "domains" {
  type        = list(string)
  description = "Which domains are we serving the site from?"
  default     = ["flakey-tests.ray.io", "flaky-tests.ray.io"]
}
