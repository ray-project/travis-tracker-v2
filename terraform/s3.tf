# Account settings

resource "aws_s3_account_public_access_block" "account" {
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Job Logs bucket

resource "aws_s3_bucket" "logs" {
  bucket = "ray-travis-logs"

  versioning {
    enabled = "true"
  }

  lifecycle {
    # Destroying this bucket will cause unrecoverable lose of build history
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket = aws_s3_bucket.logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# This allow the buildkite builders (in a different account) to put objects in the
# logs.
resource "aws_s3_bucket_policy" "logs" {
  bucket = aws_s3_bucket.logs.id

  policy = <<EOF
{
    "Version": "2012-10-17",
    "Id": "Policy1513129229074",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::029272617770:role/ray_wheels_bucket_access"
            },
            "Action": [
                "s3:PutObject",
                "s3:PutObjectAcl"
            ],
            "Resource": [
                "${aws_s3_bucket.logs.arn}",
                "${aws_s3_bucket.logs.arn}/*"
            ]
        }
    ]
}
EOF
}


# Website Bucket

resource "aws_s3_bucket" "site" {
  bucket = "ray-travis-site"

  versioning {
    enabled = "true"
  }

  lifecycle {
    # Destroying this bucket will cause the site to go offline
    prevent_destroy = true
  }

  lifecycle_rule {
    id      = "tmp"
    prefix  = "tmp/"
    enabled = true
    expiration {
      days = 30
    }
  }
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}


resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id

  # Note: we need both List & Get to make the 404s work with cloudfront
  policy = <<POLICY
{
  "Id": "PolicyForCloudFrontPrivateContent",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "${aws_cloudfront_origin_access_identity.site.iam_arn}"
      },
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "${aws_s3_bucket.site.arn}",
        "${aws_s3_bucket.site.arn}/*"
      ],
      "Sid": "read"
    }
  ],
  "Version": "2008-10-17"
}
POLICY
}
