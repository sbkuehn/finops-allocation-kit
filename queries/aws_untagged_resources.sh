#!/usr/bin/env bash
# List AWS resources missing a "team" tag using the Resource Groups Tagging API.
#
# Usage: ./queries/aws_untagged_resources.sh [region]
#
# Note: the Tagging API only returns resources that have been tagged at some
# point, or that support tagging and were created after tagging was enabled.
# Resources that have never carried any tag at all may not show up, so pair
# this with AWS Config's required-tags managed rule for full coverage.
set -euo pipefail

REGION="${1:-us-east-1}"

aws resourcegroupstaggingapi get-resources \
  --region "$REGION" \
  --output json \
  | jq -r '
      .ResourceTagMappingList[]
      | select(
          ([.Tags[]? | select((.Key | ascii_downcase) == "team")] | length) == 0
          and
          ([.Tags[]? | select((.Key | ascii_downcase) == "shared" and (.Value | ascii_downcase) == "true")] | length) == 0
        )
      | .ResourceARN
    '
