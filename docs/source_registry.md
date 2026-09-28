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
| ASOS/METAR/NCEI | Surface truth | Visibility, snow, wind/gust |
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
