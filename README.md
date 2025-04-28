# Do Appalachian hillslopes look like modern permafrost hillslopes?
Short answer - yes! in that they are longer and more planar when they are colder. So we are asking <i>Geology</i> to let us publish a paper that says that. 

# Contents
* Please note that this is an uncharacteristically messy repo because it's work smeared over 3 institutions and 6 years, sometimes happened on an HPC environment, sometimes happened on my local machine, and involves collaboration with an undergrad student. Apologies, but you should get the gist of what we've done here. 

The only thing I've done by hand is select plunging anticlines of the Tuscarora up and down PA, MD, WV, and VA, and those areas of interest can be found in `tiles_3dep_realigned.shp` and associated assets (their centroids are also foudn in `output_data.csv`). 

Basically all the erosion rate data was compiled from previous literature, namely Portenga and Bierman of various years. Geology shapefiles come from the USGS [Mineral Resources Online Spatial Data Access Tool](https://mrdata.usgs.gov/). 

The directory  `/output_data` has the reduced "results" that can be parsed further and are cleaned up as a Data Repository for submission. 

# Analysis scripts
## Notebooks
I like notebooks.
- `data_compilation.ipynb` does a few things: (1) finds all the occurrences of the Tuscarora Sandstone/Quartzite, (2) compiles all of Paul Bierman's labs' data on the Mid-Atlantic, (3) basically does a bunch of split-apply-combine data analysis and visualizations of already-published data, plus (4) creates AOIs for ridgeline erosion rates to query 3DEP point clouds to build DEMs for LSDTT. 
- 'lsdtt_results_reduction.ipynb` ingests the output of `lsdtt-dask-delayed.py` so that it can be plotted up nicely later...
- 'lsdtt_results_plots.ipynb` takes the reduced data outputs from the big ol algorithm and combines it with the (paleo)climate maps and other data for interpretation
- `map_figures.ipynb` just makes the nice maps. 

## Python scripts
I wrote two scripts that use `dask` to run computationally intensive (but parallel) tasks on our HPC environment. 
- `get_3dep_tiles_dask_delayed.py` will ingest areas of interest and use [OpenTopography's workflow](https://github.com/OpenTopography/OT_3DEP_Workflows) to download 3DEP point clouds, turn them in to a DTM, and then fill some gaps before sending them to `lsdtt-dask-delayed.py`.
-  `lsdtt-dask-delayed.py` will write driver files and run the CLI tool for [LSDTopoTools](https://github.com/LSDtopotools) basic topographic metrics and advanced hillslope analysis. 

## Bonus! `structure` directory
This is the work of W&M undergraduate Kinsey Shefelton who worked tirelessly to collect and even digitize old maps to get as many strikes and dips and fold axes as we could find. 