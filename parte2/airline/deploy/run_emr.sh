#!/bin/bash
# Uso: BUCKET=mi-bucket bash deploy/run_emr.sh     (desde CloudShell o tu PC con credenciales del lab)
set -e
: "${BUCKET:?define BUCKET}"
aws s3 cp emr/curate_job.py s3://$BUCKET/code/curate_job.py
CID=$(aws emr create-cluster --name airline-batch --release-label emr-7.2.0 \
  --applications Name=Spark --use-default-roles \
  --instance-type m4.large --instance-count 2 \
  --log-uri s3://$BUCKET/emr-logs/ --auto-terminate \
  --steps "Type=Spark,Name=curate,ActionOnFailure=TERMINATE_CLUSTER,Args=[--deploy-mode,cluster,s3://$BUCKET/code/curate_job.py,s3://$BUCKET/raw/,s3://$BUCKET/curated,s3://$BUCKET/metrics]" \
  --query ClusterId --output text)
echo "Cluster: $CID"
aws emr wait cluster-terminated --cluster-id $CID
aws emr describe-cluster --cluster-id $CID --query 'Cluster.[Status.State,Status.StateChangeReason.Message,NormalizedInstanceHours]'
