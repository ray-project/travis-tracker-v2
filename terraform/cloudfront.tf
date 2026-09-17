locals {
  s3_origin_id = "S3-ray-travis-site"
}

resource "aws_cloudfront_distribution" "site" {
  enabled = "true"

  aliases = var.domains

  origin {
    origin_id = local.s3_origin_id

    domain_name = aws_s3_bucket.site.bucket_regional_domain_name
    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.site.cloudfront_access_identity_path
    }
  }

  default_root_object = "index.html"
  custom_error_response {
    error_caching_min_ttl = "0"
    error_code            = "404"
    response_code         = "404"
    response_page_path    = "/404.html"
  }

  default_cache_behavior {
    target_origin_id       = local.s3_origin_id
    allowed_methods        = ["HEAD", "GET"]
    cached_methods         = ["HEAD", "GET"]
    compress               = "true"
    default_ttl            = "300" # 60s * 5m
    max_ttl                = "600" # 60s * 10m
    min_ttl                = "0"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = false

      cookies {
        forward = "none"
      }
    }

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.directory_index.arn
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.site.arn
    minimum_protocol_version = "TLSv1.2_2019"
    ssl_support_method       = "sni-only"
  }

  is_ipv6_enabled = "true"

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  lifecycle {
    # Altering this in prod involves extra manual work. Please be sure you want to do this :D
    prevent_destroy = true
  }

  depends_on = [aws_acm_certificate_validation.site]
  provider   = aws.cloudfront
}

resource "aws_cloudfront_origin_access_identity" "site" {
  comment = "access-identity-ray-travis-site"
}


# Rewrites /foo and /foo/ to /foo/index.html. Without this, every route except
# the site root 404s: default_root_object only applies to "/", and the S3 REST
# origin does not resolve index documents. See directory-index.js.
resource "aws_cloudfront_function" "directory_index" {
  name    = "ray-travis-site-directory-index"
  runtime = "cloudfront-js-1.0"
  comment = "Resolve directory-style URLs to index.html"
  publish = true
  code    = file("${path.module}/directory-index.js")

  # Matches the distribution: CloudFront is managed through us-east-1.
  provider = aws.cloudfront
}
