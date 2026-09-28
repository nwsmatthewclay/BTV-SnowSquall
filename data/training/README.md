# Training Dataset

The final ML matrix will contain one row per tracked radar object per scan time.

The current verified seed is the 36-case Banacos et al. (2014) northern NY/VT snow-squall climatology. It contains published event timing, observing station, visibility, wind, temperature, and hybrid-event metadata.

This event table is not itself the ML matrix. Reconstruction must turn each event into scan-by-scan radar objects, attach environment and surface observations, and create future-event targets.

The Southern New England 1994-2018 climatology contributes a separate 100-event positive population.