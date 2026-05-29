#!/bin/bash
# CaseReady — one-command deploy to AWS
# Prerequisites: AWS CLI configured, Docker running, SAM CLI installed
#
# Usage:
#   ./infra/deploy.sh staging
#   ./infra/deploy.sh production

set -e

ENV=${1:-staging}
REGION=${AWS_DEFAULT_REGION:-us-east-1}
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/caseready-$ENV"
SAM_BUCKET="caseready-sam-artifacts-$ACCOUNT_ID"

echo "==> Deploying CaseReady [$ENV] to $REGION"

# 1. Create S3 bucket for SAM artifacts if it doesn't exist
aws s3 mb "s3://$SAM_BUCKET" --region "$REGION" 2>/dev/null || true

# 2. Create ECR repo if it doesn't exist
aws ecr describe-repositories --repository-names "caseready-$ENV" --region "$REGION" 2>/dev/null || \
  aws ecr create-repository --repository-name "caseready-$ENV" --region "$REGION"

# 3. Authenticate Docker to ECR
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# 4. Build and push container image
docker build -t "caseready-$ENV" .
docker tag "caseready-$ENV:latest" "$ECR_URI:latest"
docker push "$ECR_URI:latest"

# 5. SAM deploy
sam deploy \
  --template-file infra/template.yaml \
  --stack-name "caseready-$ENV" \
  --region "$REGION" \
  --s3-bucket "$SAM_BUCKET" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment="$ENV" \
  --no-fail-on-empty-changeset

# 6. Print the API URL
echo ""
echo "==> Deployed. API URL:"
aws cloudformation describe-stacks \
  --stack-name "caseready-$ENV" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
  --output text
