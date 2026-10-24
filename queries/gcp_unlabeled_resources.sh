#!/usr/bin/env bash
# List GCP resources missing a "team" label using Cloud Asset Inventory.
#
# Usage: ./queries/gcp_unlabeled_resources.sh organizations/123456789012
#        ./queries/gcp_unlabeled_resources.sh projects/my-project
#
# Requires roles/cloudasset.viewer on the scope. GCP labels are lowercase by
# rule, so at least you're spared the casing mess here.
set -euo pipefail

SCOPE="${1:?Pass a scope like organizations/ORG_ID or projects/PROJECT_ID}"

gcloud asset search-all-resources \
  --scope="$SCOPE" \
  --query='NOT labels.team:* AND NOT labels.shared=true' \
  --format='table(assetType, name.basename(), location, project)'
