output "bucket_name" {
  value       = aws_s3_bucket.terraform_state.bucket
  description = "The name of the bucket"
}

output "bucket_arn" {
  value       = aws_s3_bucket.terraform_state.arn
  description = "The ARN of the bucket"
}