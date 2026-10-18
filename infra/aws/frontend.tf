resource "aws_s3_bucket" "frontend" {
  bucket        = "${local.name}-${local.account_id}-${var.aws_region}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${local.name}-web"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "spa" {
  name    = "${local.name}-spa"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = file("${path.module}/spa.js")
}

resource "aws_cloudfront_cache_policy" "static" {
  name        = "${local.name}-origin-cache-headers"
  min_ttl     = 0
  default_ttl = 0
  max_ttl     = 31536000
  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

resource "aws_cloudfront_origin_request_policy" "api" {
  name = "${local.name}-authenticated-api"
  cookies_config {
    cookie_behavior = "none"
  }
  headers_config {
    header_behavior = "allViewerAndWhitelistCloudFront"
    headers {
      items = ["CloudFront-Forwarded-Proto"]
    }
  }
  query_strings_config {
    query_string_behavior = "all"
  }
}

resource "aws_cloudfront_response_headers_policy" "security" {
  name = "${local.name}-security"
  security_headers_config {
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "no-referrer"
      override        = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }
    content_security_policy {
      content_security_policy = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://cognito-idp.${var.aws_region}.amazonaws.com https://*.auth.${var.aws_region}.amazoncognito.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self' https://*.auth.${var.aws_region}.amazoncognito.com; upgrade-insecure-requests"
      override                = true
    }
  }
}

resource "aws_cloudfront_vpc_origin" "api" {
  vpc_origin_endpoint_config {
    name                   = "${local.name}-api"
    arn                    = aws_lb.api.arn
    http_port              = 80
    https_port             = 443
    origin_protocol_policy = "http-only"
    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1
    }
  }
  depends_on = [aws_lb_listener.api, aws_internet_gateway.app]
}

data "aws_security_group" "cloudfront_origin" {
  filter {
    name   = "vpc-id"
    values = [aws_vpc.app.id]
  }
  filter {
    name   = "group-name"
    values = ["CloudFront-VPCOrigins-Service-SG"]
  }
  depends_on = [aws_cloudfront_vpc_origin.api]
}

resource "aws_vpc_security_group_ingress_rule" "alb_from_cloudfront" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = data.aws_security_group.cloudfront_origin.id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

resource "aws_cloudfront_distribution" "app" {
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  comment             = "${local.name}: HTTPS edge, private API origin"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  wait_for_deployment = true

  origin {
    origin_id                = "web"
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  origin {
    origin_id   = "api"
    domain_name = aws_lb.api.dns_name
    vpc_origin_config {
      vpc_origin_id            = aws_cloudfront_vpc_origin.api.id
      origin_keepalive_timeout = 5
      origin_read_timeout      = 60
    }
  }

  default_cache_behavior {
    target_origin_id           = "web"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    viewer_protocol_policy     = "redirect-to-https"
    compress                   = true
    cache_policy_id            = aws_cloudfront_cache_policy.static.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa.arn
    }
  }

  ordered_cache_behavior {
    path_pattern               = "/api/*"
    target_origin_id           = "api"
    allowed_methods            = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods             = ["GET", "HEAD"]
    viewer_protocol_policy     = "https-only"
    compress                   = true
    cache_policy_id            = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id   = aws_cloudfront_origin_request_policy.api.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }

  dynamic "custom_error_response" {
    for_each = { for code in [400, 403, 404, 405, 414, 416, 500, 501, 502, 503, 504] : tostring(code) => code }
    content {
      error_code            = custom_error_response.value
      error_caching_min_ttl = 0
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
  viewer_certificate {
    cloudfront_default_certificate = true
  }
  depends_on = [aws_vpc_security_group_ingress_rule.alb_from_cloudfront]
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "CloudFrontRead"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.frontend.arn}/*"
        Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.app.arn } }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.frontend.arn, "${aws_s3_bucket.frontend.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }
    ]
  })
}
