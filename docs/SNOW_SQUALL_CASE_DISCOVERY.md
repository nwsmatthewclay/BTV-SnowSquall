# Snow Squall Case Discovery

This project uses a case-funnel rather than a single binary truth list.

## Evidence tiers

**Study verified**
Curated historical cases identified and manually checked in Banacos et al. (2014), including the complete 36-event BTV-area inventory. These cases are preserved as seed cases and remain traceable to the published table.

**Official documented**
NCEI Storm Events records whose event type or narrative explicitly identifies a snow squall. NCEI screening hits such as whiteout/flash-freeze language without an explicit snow-squall identification are kept separate.

**Warning verified**
IEM/COW Snow Squall Warning records with the IEM verification flag indicating LSR-based warning verification. The warning is still treated as an evidence source rather than perfect event truth.

**Warning only**
An NWS Snow Squall Warning without independent LSR verification.

**Report only / screening**
SWDI Preliminary Local Storm Reports and NCEI screening-language candidates. These are useful for finding missed events but are never promoted to training truth solely because they exist.

## Source policy

NCEI Storm Events supplies official documented event records. NOAA SWDI PLSR is preliminary evidence and is not equivalent to authoritative ground truth. IEM COW warning verification is an independent evidence flag, not a scientific truth label.

The discovery engine also retains source overlap, warning timing, report counts, event windows, and radar proximity. Negative space is never interpreted as proof that a snow squall did not occur.

## Training policy

The first expanded training set may use the strongest evidence tiers after radar reconstruction and label QC. Warning-only, report-only, and screening candidates remain available for review, hard-negative analysis, and future verification.

Modern independent validation cases are explicitly excluded from case selection and are never eligible for historical training.

## Radar policy

Each candidate gets a reproducible case window and a nearest-plausible-radar assignment. The current expansion run uses KCXX or KTYX, one radar per candidate, to keep initial acquisition volume controlled. Additional radar coverage can be added deliberately for cases where dual-radar analysis is scientifically useful.

## Scaling

The expansion selector supports offsets so batches can be harvested repeatedly without replacing the entire population. The intended workflow is:

discovery -> ledger audit -> case review -> radar acquisition -> object reconstruction -> environment attachment -> outcome labels -> feature generation -> grouped cross-validation -> independent validation -> live shadow scoring.

No candidate model is operationally enabled by the discovery process itself.
