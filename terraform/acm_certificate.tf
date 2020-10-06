resource "aws_acm_certificate" "site" {
  domain_name = var.domains[0]

  subject_alternative_names = slice(var.domains, 1, length(var.domains)) # Ugh
  validation_method         = "DNS"

  provider = aws.cloudfront
}


resource "aws_acm_certificate_validation" "site" {
  provider = aws.cloudfront

  certificate_arn = aws_acm_certificate.site.arn

  # TODO: For whenever we can manage these domains in route53
  # validation_record_fqdns = []
}
