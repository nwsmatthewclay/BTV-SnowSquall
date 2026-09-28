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
