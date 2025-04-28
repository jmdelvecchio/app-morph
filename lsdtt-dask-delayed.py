import shutil 

from pathlib import Path

import os

import dask
from time import sleep

### SLURMIN ####

def make_basic_driver(tile):
    tile_string = str(tile.stem) 
    print(f'Making driver for {tile_string}')
    x = f"""#channel heads

    write path: ./lsdtt/results/{tile_string}/
    read path: ./appalachia/dem_tiles/

    read fname: {tile_string}
    write fname: {tile_string}_100m

    write_hillshade: true

    # Table A4
    print_wiener_filtered_raster: true

    #Table A5
    surface_fitting_radius: 100
    print_smoothed_elevation: true
    print_curvature: true
    print_planform_curvature: false
    print_profile_curvature: false
    print_tangential_curvature: true

    #Table A7
    print_dinf_drainage_area_raster: true
    print_d8_drainage_area_raster: true

    print_area_threshold_channels: false"""

    with open(f"./lsdtt/results/{tile_string}/{tile_string}_basic_100m.driver","w+") as f:
    # with open(f"./lsdtt/curvatures/{tile_string}_curv.driver","w+") as f:
        print(f)
        f.writelines(x)

def make_channel_driver(tile):
    tile_string = str(tile.stem) 
    print(f'Making driver for {tile_string}')
    x = f"""#channel heads

    write path: ./lsdtt/results/{tile_string}/
    read path: ./appalachia/dem_tiles/

    read fname: {tile_string}
    write fname: {tile_string}

    write_hillshade: false

    # Parameters for drainage area
    min_slope_for_fill: 0.0001

    # Basic channel network
    threshold_contributing_pixels: 500
    print_channels_to_csv: true
    print_sources_to_csv: true

    print_dreich_threshold_channels: false

    print_wiener_channels: true

    print_area_threshold_channels: false

    print_area_threshold_channels: false"""

    with open(f"./lsdtt/results/{tile_string}/{tile_string}_channels.driver","w+") as f:
        f.writelines(x)

def make_hcc_driver(tile):
    print(tile)
    tile_string = str(tile.stem) 
    x = f"""#channel heads

    write path: ./lsdtt/results/{tile_string}/
    read path: ./appalachia/dem_tiles/

    read fname: {tile_string}
    write fname: {tile_string}

    CHeads_file: {tile_string}_Wsources.csv
    

    # debug
    only_check_parameters: false

    # 2024 secret parameter?
    use_legacy_HFR: true

    # this removes everything bellow a minimum elevation (default = 0)
    remove_seas: true

    # lower = dense network and higher = sparse network
    threshold_contributing_pixels: 500
    #joanmarie consider this??

    #Table 4
    RemoveSteepHillslopes: false

    # The parameter needed for switching on hilltops metrics
    run_HFR_analysis: true
    print_hillslope_traces: false
    hillslope_trace_thinning: 10

    #Table 7
    print_basin_raster: true
    maximum_basin_size_pixels: 100000000
    #find_complete_basins_in_window: true
    #find_largest_complete_basins: false
    #test_drainage_boundaries: false

    write_hillshade: true
    #writng some outputs, you can use other options from the documentations
    write_hillslope_gradient: true
    write_hillslope_length: true 
    write_hilltops: true

    #Useful to check the channel network
    print_channels_to_csv: true

    #end of file"""

    with open(f"./lsdtt/results/{tile_string}/{tile_string}_adv.driver","w+") as f:
        f.writelines(x)

def copy_sources(tile):
    
    tile_string = str(tile.stem) 

    # Source path
    source = f"./lsdtt/results/{tile_string}/{tile_string}_Wsources.csv"
    print(f'source is {source}')
    
    # Destination path
    destination = f"./appalachia/dem_tiles/{tile_string}_Wsources.csv"
    print(f'dest is {destination}')

    # Copy the content of
    # source to destination
    try:
        shutil.copy(source, destination)
    except FileNotFoundError:
        print(f"Huh no channels for {tile.stem} OK")
# Function to process each ID in parallel
def process_tile(tile):
    print(f'Processing tile: {tile}')
    tile_string = str(tile.stem) 
    Path(f'./lsdtt/results/{tile_string}').mkdir(parents=True, exist_ok=True)
    
    # __ = make_basic_driver(tile)
    # __ = make_channel_driver(tile)
    # __ = copy_sources(tile)
    # __ = make_hcc_driver(tile)
  

    # lsd_string=f"lsdtt-basic-metrics lsdtt/results/{tile_string}/{tile_string}_basic_100m.driver"
    # os.system(lsd_string)
    # lsd_string=f"lsdtt-channel-extraction lsdtt/results/{tile_string}/{tile_string}_channels.driver"
    # os.system(lsd_string)
    lsd_string=f"lsdtt-hillslope-channel-coupling lsdtt/results/{tile_string}/{tile_string}_adv.driver"
    os.system(lsd_string)

if __name__ == "__main__" : 
    p = Path('./appalachia/dem_tiles/')
    tile_list = sorted(p.glob('tile_*_filled.tif'))

    print(tile_list)

    #########################
    delayed_tasks = []

    for tile in tile_list:
        delayed_task = dask.delayed(process_tile)(tile)
        delayed_tasks.append(delayed_task)

    # Execute the delayed tasks in parallel
    results = dask.compute(*delayed_tasks)

    # ###########################
    # for tile in tile_list:    
    #     print(f'Processing tile: {tile}')
    
    #     # Path(f'./lsdtt/{tile}/').mkdir(parents=True, exist_ok=True)

    #     __ = make_basic_driver(tile)
    #     tile_string = str(tile.stem) 
    #     lsd_string=f"lsdtt-basic-metrics lsdtt/curvatures/{tile_string}_curv.driver"
    #     os.system(lsd_string)
