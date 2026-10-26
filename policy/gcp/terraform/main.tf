# Terraform version of the custom constraints in policy/gcp/.
# Same rules, managed in version control next to the rest of your landing zone.
#
#   terraform init
#   terraform apply -var="org_id=123456789012"                 # dry run
#   terraform apply -var="org_id=123456789012" -var="enforce=true"

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

locals {
  parent = "organizations/${var.org_id}"

  constraints = {
    "custom.requireAllocationLabels" = {
      display_name = "Require allocation labels"
      description  = "Resources must carry a team label (or shared=true), plus costcenter and env."
      condition    = <<-CEL
        ('team' in resource.labels ||
          ('shared' in resource.labels && resource.labels['shared'] == 'true')) &&
        'costcenter' in resource.labels &&
        'env' in resource.labels
      CEL
    }
    "custom.allowedEnvValues" = {
      display_name = "Allowed env label values"
      description  = "The env label, when present, must be prod, staging, or dev."
      condition    = "!('env' in resource.labels) || resource.labels['env'] in ['prod', 'staging', 'dev']"
    }
  }
}

resource "google_org_policy_custom_constraint" "allocation" {
  for_each = local.constraints

  name           = each.key
  parent         = local.parent
  display_name   = each.value.display_name
  description    = each.value.description
  condition      = trimspace(each.value.condition)
  action_type    = "ALLOW"
  method_types   = ["CREATE"]
  resource_types = var.resource_types
}

resource "google_org_policy_policy" "allocation" {
  for_each = google_org_policy_custom_constraint.allocation

  name   = "${local.parent}/policies/${each.value.name}"
  parent = local.parent

  # Enforced: deny non-compliant creates
  dynamic "spec" {
    for_each = var.enforce ? [1] : []
    content {
      rules {
        enforce = "TRUE"
      }
    }
  }

  # Dry run: log violations only
  dynamic "dry_run_spec" {
    for_each = var.enforce ? [] : [1]
    content {
      rules {
        enforce = "TRUE"
      }
    }
  }
}
