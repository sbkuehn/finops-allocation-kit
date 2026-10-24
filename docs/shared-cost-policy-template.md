# Shared Cost Allocation Policy (Template)

**Owner:** _name, role_
**Approved by:** _finance lead_, _engineering lead_
**Effective:** _date_
**Review cadence:** quarterly

Copy this, fill in the blanks, and get both finance and engineering to sign off before showback numbers go out. The point of writing this down is so that "why did my number change?" has an answer that lives somewhere other than one person's head.

## 1. What we report

We run **showback** for all teams. We run **chargeback** only for the teams listed below, and only for the cost categories marked "allocated" in section 3.

| Team | Showback | Chargeback | Since |
|---|---|---|---|
| _payments_ | Yes | Pilot | _date_ |
| _everyone else_ | Yes | No | |

## 2. Which cost number we use

We allocate using **_EffectiveCost_ / _ListCost_** from our FOCUS export. (Pick one and delete the other.)

- If **EffectiveCost**: teams receive the benefit of commitment discounts (Reserved Instances, Savings Plans, CUDs) on the usage they consume. Unused commitment is held centrally by _team_.
- If **ListCost**: teams see on-demand rates. The difference between list and effective is reported as a central savings line owned by _team_.

We will not switch between these mid-year without notice to every team that receives showback.

## 3. Shared costs: allocated or central

| Cost category | Treatment | Method | Weight source |
|---|---|---|---|
| Shared Kubernetes node pools | Allocated | Proportional | CPU-seconds by namespace |
| Shared GPU / inference pools | Allocated | Proportional | GPU-hours by workload |
| Shared AI gateways (token APIs) | Allocated | Proportional | Estimated token cost by caller |
| Enterprise support plan | Central | Not allocated | |
| Security tooling | Central | Not allocated | |
| Platform team tooling | _decide_ | | |

Anything tagged `shared=true` without a weighting falls into the `UNALLOCATED_NO_WEIGHT` bucket until a weighting exists. We do not even-split as a permanent answer.

## 4. Untagged resources

Resources with no `team` tag and no `shared=true` tag land in `UNALLOCATED`. _Name_ owns driving that bucket down and reviews it monthly.

## 5. Disputes

Teams can dispute their showback within _10 business days_ of publication by _process_. Corrections are applied to the next cycle, not retroactively, unless the error exceeds _X%_ of the team's total.

## 6. Metrics we publish

- Allocation coverage (target: _90%_), tracked monthly
- Size of `UNALLOCATED` and `UNALLOCATED_NO_WEIGHT` buckets
- Number of open tag drift findings
