#!/usr/bin/env bash
# Register the custom constraints in this folder and set a policy for each.
#
# Usage:
#   ./policy/gcp/deploy.sh ORG_ID            # dry run (log violations, block nothing)
#   ./policy/gcp/deploy.sh ORG_ID --enforce  # actually deny non-compliant creates
#
# Start with the dry run, the same way you'd start Azure Policy in Audit mode.
# Watch the violations in Cloud Logging for a couple of weeks, clean up the
# pipelines that would break, then rerun with --enforce.
#
# Requires roles/orgpolicy.policyAdmin at the organization.
set -euo pipefail

ORG_ID="${1:?Pass your numeric organization ID}"
MODE="${2:-}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for file in "$DIR"/*.yaml; do
  constraint="$(grep -E '^name:' "$file" | sed -E 's#.*/customConstraints/##')"
  echo "Registering $constraint"
  sed "s/ORG_ID/${ORG_ID}/g" "$file" | gcloud org-policies set-custom-constraint /dev/stdin

  if [[ "$MODE" == "--enforce" ]]; then
    spec_key="spec"
    echo "Enforcing $constraint"
  else
    spec_key="dryRunSpec"
    echo "Setting $constraint to dry run"
  fi

  gcloud org-policies set-policy /dev/stdin --organization="$ORG_ID" <<EOF
name: organizations/${ORG_ID}/policies/${constraint}
${spec_key}:
  rules:
  - enforce: true
EOF
done

echo
echo "Done. Dry-run violations show up in Cloud Logging under the"
echo "orgpolicy.googleapis.com audit logs with a dry-run marker."
