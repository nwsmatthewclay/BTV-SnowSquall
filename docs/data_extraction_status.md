# Data Extraction Status

## Verified and extracted

### Banacos et al. (2014)
- 36 event records extracted from published Table 2.
- Raw ASOS wind group preserved alongside derived peak gust.
- Observing stations: KBTV, KMPV, KMSS.
- Event start time, visibility, visibility-duration fields, temperatures, hybrid flag, and peak wind are retained.
- Published methodology states that candidate METAR hourly/special observations were compared against 2-km composite reflectivity to identify narrow convective bands.
- The study also used NARR environmental data and a 2005-06 winter control dataset.

### Southern New England (Colby et al. 2022)
- 100-event population metadata extracted: 72 Classic, 15 Atlantic, 9 Northern, 4 Special.
- Domain and event definition recorded.
- Methodology confirms METAR, NEXRAD Level II, radar cell tracking, WPC analyses, and hourly ERA5.
- Exact 100 case dates are deliberately not populated yet; they must be extracted from the authors' underlying event catalog or machine-readable supplementary data rather than inferred from figures.

## Next extraction

1. Acquire native Level II volumes for the 36 BTV cases.
2. Acquire ASOS/METAR observations around each case.
3. Reconstruct radar object tracks.
4. Match NARR/ERA5/RAP environmental fields.
5. Build null-object population from control periods.
6. Extract the 100 Southern New England event dates and radar windows.
