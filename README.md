# FinOps Allocation Kit

**Author:** Shannon Eldridge-Kuehn
**Date:** October 24, 2026
**Companion to:** *Showback, Chargeback, and Allocation: The FinOps Ladder Nobody Gets to Skip* on [Cloudy Musings](https://shankuehn.io)

This repo is the hands-on half of that post. The post makes the argument that allocation is the layer everything else in FinOps sits on, and that you should build an allocation coverage metric long before anyone sends a chargeback invoice. This kit gives you the pieces to actually do that against FOCUS-formatted billing data: flatten the tags, allocate direct and shared costs, track coverage over time, catch tag drift, and turn AI gateway telemetry into weights so token spend stops landing in the "nobody owns this" pile.

Everything runs against a synthetic sample export out of the box, so you can kick the tires before pointing it at real billing data.

## What's in here

```
finops-allocation-kit/
├── scripts/
│   ├── generate_sample_data.py   # synthetic FOCUS-shaped export (6 months, 5 teams)
│   ├── flatten_tags.py           # FOCUS Tags JSON -> x_Team, x_CostCenter, etc.
│   ├── allocate.py               # tag-and-fallback allocation + coverage
│   ├── coverage_trend.py         # coverage month over month, optional PNG
│   ├── validate_weights.py       # catch weights that don't sum to 1 (and friends)
│   └── tag_drift.py              # ownership tags that changed between periods
├── examples/
│   ├── focus_export_sample.csv       # generated sample export
│   ├── shared_resource_weights.csv   # usage weights for shared k8s + GPU pool
│   ├── gateway_token_usage.csv       # sample AI gateway telemetry
│   └── token_usage_to_weights.py     # token logs -> allocation weights
├── policy/
│   ├── azure/   # Azure Policy: require tags, inherit from resource group
│   ├── aws/     # Tag Policy for value consistency + SCP to require presence
│   └── gcp/     # custom org policy constraints, deploy script, Terraform
├── queries/     # find untagged stuff in Azure (KQL), AWS, and GCP
├── docs/
│   └── shared-cost-policy-template.md   # the written policy finance will ask for
└── tests/
```

## Quick start

```bash
git clone https://github.com/sbkuehn/finops-allocation-kit.git
cd finops-allocation-kit
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Regenerate the sample data (optional, it's already in examples/)
python scripts/generate_sample_data.py

# Allocate September
python scripts/allocate.py examples/focus_export_sample.csv \
  --weights examples/shared_resource_weights.csv \
  --period 2026-09-01
```

You'll get something like this:

```
                 Team  AllocatedCost
          ml-research      11,239.13
             payments       9,696.90
               search       9,188.32
              CENTRAL       7,694.85
        data-platform       7,671.09
UNALLOCATED_NO_WEIGHT       6,487.26
          UNALLOCATED       3,442.07
               mobile       3,135.51

Cost column:          EffectiveCost
Total allocated:      58,555.13
Allocation coverage:  83.0%
```

## How allocation works here

Every cost row lands in exactly one bucket. I wanted the logic to be boring and explainable, because "the script decided" is not an answer anyone in a budget meeting will accept.

| Bucket | When a row lands here | Counts against coverage? |
|---|---|---|
| A team name | Row has a `team` tag. An explicit team tag always wins. | No |
| `CENTRAL` | Tagged `allocation=central`, meaning your written policy keeps it on the central budget (enterprise support, security tooling) | No, it's a deliberate decision |
| Split across teams | Tagged `shared=true` and has a usage weighting | No |
| `UNALLOCATED_NO_WEIGHT` | Tagged `shared=true` but nobody has built the weighting yet | Yes |
| `UNALLOCATED` | No team, not shared, not central | Yes |

**Allocation coverage** is everything except those last two buckets, divided by total cost. A documented central bucket is a policy choice. An untagged VM nobody can explain is an accident. Only the accidents count against you.

### Picking a cost column

This is the commitment discount question from the post, and the kit makes you choose on purpose with `--cost-column`:

- `EffectiveCost` (default): amortized, with RI/Savings Plan/CUD discounts flowing to whoever consumed them
- `ListCost`: on-demand rates, so finance keeps the discount as its own lever
- `BilledCost`: what hit the invoice on that line. Good for reconciling against the bill, confusing for showback, because commitment purchases show up as their own lines

Run the same month both ways and look at how much the team numbers move. That gap is exactly the "why did my number change 20%?" conversation you want to have once, in writing, instead of every quarter.

```bash
python scripts/allocate.py examples/focus_export_sample.csv \
  --weights examples/shared_resource_weights.csv \
  --period 2026-09-01 --cost-column ListCost
```

### The fallback switch

`--fallback bucket` (default) parks unweighted shared costs in `UNALLOCATED_NO_WEIGHT` where you can see them. `--fallback even` splits them evenly across every team with direct spend. Even split is fine as a placeholder while you build real weights. I would not leave it there long, and the teams paying for it won't want you to either.

## Coverage over time

```bash
python scripts/coverage_trend.py examples/focus_export_sample.csv \
  --weights examples/shared_resource_weights.csv \
  --png coverage_trend.png
```

```
BillingPeriodStart  TotalCost  UnallocatedCost Coverage CoverageChange
        2026-04-01   47670.33         10199.25    78.6%
        2026-05-01   51826.15         10794.97    79.2%       +0.6 pts
        2026-06-01   53602.17          9928.86    81.5%       +2.3 pts
        2026-07-01   54635.89          9127.02    83.3%       +1.8 pts
        2026-08-01   57371.12         10102.40    82.4%       -0.9 pts
        2026-09-01   58555.13          9929.33    83.0%       +0.7 pts
```

The sample data has a story baked in. Someone fixes one untagged resource every month, so you'd expect coverage to climb steadily. It doesn't, and the reason is the shared AI gateway: its spend grows every month, it has no weighting, and it quietly eats every gain the tag cleanup makes. That's the 2026 allocation problem in one table.

### Fixing the AI gateway

The gateway's billing line has no owner, but its request logs do. `token_usage_to_weights.py` turns gateway telemetry into weights, by estimated token cost by default (so a team hammering a cheap model doesn't subsidize a team calling the expensive one) or by raw tokens with `--by-tokens`.

```bash
cp examples/shared_resource_weights.csv weights_with_ai.csv
python examples/token_usage_to_weights.py examples/gateway_token_usage.csv \
  --resource aoai-shared-gateway | tail -n +2 >> weights_with_ai.csv

python scripts/coverage_trend.py examples/focus_export_sample.csv \
  --weights weights_with_ai.csv
```

September jumps from 83.0% to 94.1%. One weighting file did more than six months of tag cleanup, which is a pretty good argument for going after the big shared costs before chasing orphaned public IPs.

## Keeping the inputs honest

**Validate weights before they touch a report** - Weights that sum to 1.2 create money out of thin air, and weights that sum to 0.8 make it disappear. The validator exits non-zero on errors so you can put it in a pipeline.

```bash
python scripts/validate_weights.py examples/shared_resource_weights.csv \
  --export examples/focus_export_sample.csv
```

**Watch for tag drift, not just tag presence** - A resource tagged correctly six months ago may be running a completely different team's workload today. `tag_drift.py` flags ownership tags that were added, removed, or changed between two periods, plus resources whose owner stayed the same while cost jumped 50% or more (a common sign of a repurposed resource nobody re-tagged).

```bash
python scripts/tag_drift.py examples/focus_export_sample.csv \
  --from 2026-08-01 --to 2026-09-01
```

## Enforcing tags at creation time

The cheapest tag remediation project is the one you never have to run.

**Azure** `policy/azure/require-allocation-tags.json` requires either `team` or `shared=true`, plus `costcenter` and `env`. It defaults to `Audit`. Leave it there a couple of weeks, look at the compliance numbers, then flip to `Deny`. `inherit-tags-from-rg.json` copies tags from the resource group when they're missing, which takes a lot of the sting out of `Deny`.

```bash
az policy definition create --name require-allocation-tags \
  --rules <(jq '.properties.policyRule' policy/azure/require-allocation-tags.json) \
  --params <(jq '.properties.parameters' policy/azure/require-allocation-tags.json) \
  --mode Indexed
```

**AWS** This one trips people up. Tag Policies enforce that tag *values* are consistent (no `Payments` vs `payments`), but they don't require a tag to exist. For that you need an SCP that denies create calls when `aws:RequestTag/team` is null. Both are in `policy/aws/`. Use them together.

**GCP** GCP doesn't ship a built-in "require this label" constraint, so you write a custom organization policy constraint: a small YAML file with a CEL condition that runs on every create. `policy/gcp/` has two of them, mirroring the Azure and AWS files:

- `require-allocation-labels.yaml` requires `team` (or `shared=true`), plus `costcenter` and `env`
- `allowed-env-values.yaml` keeps `env` to `prod`, `staging`, or `dev`, like the AWS Tag Policy does for values

`deploy.sh` registers both and puts them in dry run by default, which logs violations without blocking anything (think Azure Policy in Audit mode). Rerun with `--enforce` once the logs look clean.

```bash
./policy/gcp/deploy.sh 123456789012             # dry run
./policy/gcp/deploy.sh 123456789012 --enforce   # deny non-compliant creates
```

If you'd rather keep these in your landing zone code, `policy/gcp/terraform/` does the same thing with `google_org_policy_custom_constraint` and `google_org_policy_policy`, flipping between dry run and enforce with one variable.

Two GCP-specific things to know. First, custom constraints only work on resource types each service has published support for, so unlike Azure Policy there's no single rule that blankets everything. The files cover Compute Engine instances and disks; check each service's custom constraints page before adding more types. Second, there's no equivalent of Azure's `modify` effect for inheriting labels from a project, so defaults have to come from your IaC modules instead. For labels on objects *inside* GKE clusters, use Policy Controller (managed OPA Gatekeeper), since org policy only sees the cloud resources.

## Finding what's already untagged

| Cloud | File | How to run |
|---|---|---|
| Azure | `queries/azure_untagged_resources.kql` | Resource Graph Explorer, or `az graph query -q "$(cat queries/azure_untagged_resources.kql)"` |
| Azure | `queries/azure_untagged_by_type.kql` | Same, shows where remediation pays off |
| AWS | `queries/aws_untagged_resources.sh` | `./queries/aws_untagged_resources.sh us-east-1` (needs `jq`) |
| GCP | `queries/gcp_unlabeled_resources.sh` | `./queries/gcp_unlabeled_resources.sh organizations/ORG_ID` |

## Using your own FOCUS export

Most of the big providers can export FOCUS-conformant data now (Azure Cost Management exports, AWS Data Exports, GCP's FOCUS BigQuery view), though how complete each one is varies. The scripts expect these columns:

- `BillingPeriodStart`, `ResourceId`, `ServiceCategory`, `Tags`
- At least one of `EffectiveCost`, `ListCost`, `BilledCost`
- `ResourceName` is optional but makes the weights file much friendlier

If your tag keys don't match mine, edit `DEFAULT_KEY_MAP` at the top of `flatten_tags.py`. That's the one place you map "whatever your org calls a team" to `x_Team`.

## Write the policy down

`docs/shared-cost-policy-template.md` is the document I'd want signed by finance and engineering before any showback report goes out: which cost column, which shared costs get allocated and which stay central, who owns the unallocated bucket, and how disputes work. The scripts enforce the mechanics. The policy is what makes the numbers defensible.

## Running the tests

```bash
python -m pytest -q
```

The tests check that money is conserved (allocated total always equals the input total), that each bucket behaves the way the table above says, and that the validator catches bad weight sums.

## Further reading

- [FinOps Foundation: Allocation capability](https://www.finops.org/framework/capabilities/allocation/)
- [FinOps Foundation: Invoicing & Chargeback capability](https://www.finops.org/framework/capabilities/invoicing-chargeback/)
- [FOCUS specification](https://focus.finops.org/focus-specification/)
- [FOCUS spec source and validator on GitHub](https://github.com/FinOps-Open-Cost-and-Usage-Spec)
- [Microsoft Learn: Invoicing and chargeback](https://learn.microsoft.com/cloud-computing/finops/framework/manage/invoicing-chargeback)

## License

MIT. See [LICENSE](LICENSE).
