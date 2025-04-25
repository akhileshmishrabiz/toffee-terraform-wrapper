resource "aws_s3_bucket" "primary" {
  provider = aws.primary
  bucket   = "${var.project_name}-${var.environment}-${var.primary_region}"

  tags = {
    Name        = "${var.project_name}-${var.environment}"
    Environment = var.environment
    Region      = var.primary_region
  }
}

# Create S3 bucket in secondary region
resource "aws_s3_bucket" "secondary" {
  provider = aws.secondary
  bucket   = "${var.project_name}-${var.environment}-${var.secondary_region}"

  tags = {
    Name        = "${var.project_name}-${var.environment}"
    Environment = var.environment
    Region      = var.secondary_region
  }
}

# Set up replication if enabled
resource "aws_s3_bucket_replication_configuration" "replication" {
  count = var.enable_replication ? 1 : 0
  
  provider = aws.primary
  
  # Must have bucket versioning enabled first
  depends_on = [aws_s3_bucket_versioning.primary]

  role   = aws_iam_role.replication[0].arn
  bucket = aws_s3_bucket.primary.id

  rule {
    id = "entire-bucket"
    
    status = "Enabled"
    
    destination {
      bucket        = aws_s3_bucket.secondary.arn
      storage_class = "STANDARD"
    }
  }
}

resource "aws_s3_bucket_versioning" "primary" {
  provider = aws.primary
  bucket   = aws_s3_bucket.primary.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_versioning" "secondary" {
  provider = aws.secondary
  bucket   = aws_s3_bucket.secondary.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

# IAM role for replication
resource "aws_iam_role" "replication" {
  count = var.enable_replication ? 1 : 0
  
  provider = aws.primary
  name     = "${var.project_name}-${var.environment}-replication"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
      }
    ]
  })
}

# IAM policy for replication
resource "aws_iam_policy" "replication" {
  count = var.enable_replication ? 1 : 0
  
  provider = aws.primary
  name     = "${var.project_name}-${var.environment}-replication-policy"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:GetReplicationConfiguration",
          "s3:ListBucket"
        ]
        Effect = "Allow"
        Resource = [
          aws_s3_bucket.primary.arn
        ]
      },
      {
        Action = [
          "s3:GetObjectVersionForReplication",
          "s3:GetObjectVersionAcl",
          "s3:GetObjectVersionTagging"
        ]
        Effect = "Allow"
        Resource = [
          "${aws_s3_bucket.primary.arn}/*"
        ]
      },
      {
        Action = [
          "s3:ReplicateObject",
          "s3:ReplicateDelete",
          "s3:ReplicateTags"
        ]
        Effect = "Allow"
        Resource = [
          "${aws_s3_bucket.secondary.arn}/*"
        ]
      }
    ]
  })
}

# Attach the policy to the role
resource "aws_iam_role_policy_attachment" "replication" {
  count = var.enable_replication ? 1 : 0
  
  provider   = aws.primary
  role       = aws_iam_role.replication[0].name
  policy_arn = aws_iam_policy.replication[0].arn
}