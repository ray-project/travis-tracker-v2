resource "aws_iam_user" "logs_uploader" {
  name = "travis-logs-uploader"
}

resource "aws_iam_user_policy" "uploader_writeonly_logs" {
  name = "write-only-to-bucket"

  user   = aws_iam_user.logs_uploader.name
  policy = <<POLICY
{
  "Statement": [
    {
      "Action": "s3:PutObject",
      "Effect": "Allow",
      "Resource": "${aws_s3_bucket.logs.arn}/*",
      "Sid": "write"
    }
  ],
  "Version": "2012-10-17"
}
POLICY
}

resource "aws_iam_user" "site_uploader" {
  name = "travis-site-uploader"
}

resource "aws_iam_user_policy" "uploader_readonly_logs" {
  name = "readonly-logs-bucket"

  user   = aws_iam_user.site_uploader.name
  policy = <<POLICY
{
  "Statement": [
    {
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Effect": "Allow",
      "Resource": [
        "${aws_s3_bucket.logs.arn}",
        "${aws_s3_bucket.logs.arn}/*"
      ],
      "Sid": "read"
    }
  ],
  "Version": "2012-10-17"
}
POLICY
}

resource "aws_iam_user_policy" "uploader_readwrite_site" {
  name = "readwrite-site-bucket"

  user   = aws_iam_user.site_uploader.name
  policy = <<POLICY
{
  "Statement": [
    {
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Effect": "Allow",
      "Resource": [
        "${aws_s3_bucket.site.arn}",
        "${aws_s3_bucket.site.arn}/*"
      ],
      "Sid": "readwrite"
    }
  ],
  "Version": "2012-10-17"
}
POLICY
}
