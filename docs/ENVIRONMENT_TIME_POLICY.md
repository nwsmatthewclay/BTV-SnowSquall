# Historical Environment Time Policy

Every radar-object state gets an environment analysis selected from the archive
appropriate to the radar timestamp.

## Provider eras

- Before 1 April 2007 00 UTC: NARR
- 1 April 2007 through 30 April 2012: RUC
- 1 May 2012 onward: RAP

The boundary tests are explicit in the repository so an era change cannot drift
silently.

## Future-information rule

A matched analysis is valid only when its valid time is at or before the radar
scan time. The extraction layer raises an error when a future analysis is passed
as the expected valid time.

## Units

Provider-specific names are mapped onto the canonical feature schema. For
example, 0–6 km shear supplied in m/s is converted to knots before entering the
canonical shear_0_6km_kt field.

Missing provider fields remain missing; no future or cross-era analysis is used
to fabricate a value.


## MRMS historical availability

The 36-case Banacos historical manifest spans 23 March 2002 through 2 March 2011. The archived MRMS adapter begins 1 October 2014, so MRMS predictors are structurally unavailable for this historical population. Zero MRMS feature coverage in this case set must therefore be treated as an era limitation, not an acquisition failure. MRMS can be introduced for later independent cases or a separate modern verification population without backfilling values into the historical cases.
