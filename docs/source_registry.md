# Snow Squall Evidence Registry

This registry defines the sources that seed the living database. Source metadata
must be recorded before case data are treated as truth.

| Source | Role | Use |
|---|---|---|
| Banacos BTV 36-case climatology | Regional seed cases | Identify candidate BTV events |
| Southern New England 100-case climatology | Independent case population | Expand event diversity |
| Penn State SNSQ/null dataset | Environmental reference | Compare environmental discrimination |
| NEXRAD Level II KCXX/KTYX | Storm structure | 3-D radar features and evolution |
| MRMS | Precipitation context | Modern-era lowest reflectivity and precipitation accumulation; additional fields only when defensibly archived |
| RAP | Environment | SNSQ and thermodynamic/kinematic fields |
| ASOS/METAR/NCEI | Surface truth | Visibility, snow, wind/gust |\n| mPING | Independent precipitation-type QC | Case/time-linked rain, snow, mixed and freezing-precipitation evidence; never an automatic truth label |
| NWS/IEM SQW archives | Event truth | Warning polygons/timing and provenance |

## Evidence rule

MRMS availability is date-dependent: the IEM MTArchive contains selected MRMS fields back to October 2014, while older Banacos cases must retain MRMS missingness. citeturn675482search0turn540908view0

No source is automatically considered perfect truth. Labels should combine
independent evidence and retain provenance/confidence.

## Dataset construction rule

Published case lists identify where to look. They do not replace reconstruction
from observations. Every case should be reconstructed through the same pipeline
as possible null events so the model learns physical/event differences rather
than study-selection artifacts.


## mPING access and retention

mPING API access requires an API key obtained through the mPING registration process.
The workflow reads the key only from the `MPING_API_KEY` GitHub Actions secret and
fails soft when the key is absent. Persisted project evidence intentionally omits
individual report IDs and coordinates; only case-linked observation time and
predefined phenomenon fields are retained. mPING evidence is non-authoritative QC
and is never converted directly into a positive or negative snow-squall label.
