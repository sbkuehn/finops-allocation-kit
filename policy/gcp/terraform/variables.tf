variable "org_id" {
  description = "Numeric GCP organization ID"
  type        = string
}

variable "enforce" {
  description = "false = dry run (log only), true = deny non-compliant creates"
  type        = bool
  default     = false
}

variable "resource_types" {
  description = "Resource types the constraints apply to. Only add types the owning service supports for custom constraints."
  type        = list(string)
  default = [
    "compute.googleapis.com/Instance",
    "compute.googleapis.com/Disk",
  ]
}
