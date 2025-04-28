import dask
from time import sleep
#Import Modules
import copy
import geopandas as gpd
import ipyleaflet
import ipywidgets as widgets
import json
import math
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import os
from osgeo import gdal
import pdal
import pyproj
import requests
from shapely.geometry import shape, Point, Polygon
from shapely.ops import transform

import rioxarray as rio
from rasterio.enums import Resampling
import matplotlib.pyplot as plt

# jd edits
from pathlib import Path
import rasterio

# from dask.distributed import Client
# from dask_jobqueue import PBSCluster

def proj_to_3857(poly, orig_crs):
    """
    Function for reprojecting a polygon from a shapefile of any CRS to Web Mercator (EPSG: 3857).
    The original polygon must have a CRS assigned.
    
    Parameters:
        poly (shapely polygon): User area of interest (AOI)
        orig_crs (str): the original CRS (EPSG) for the shapefile. It is stripped out during import_shapefile_to_shapely() method

    Returns:
        user_poly_proj4326 (shapely polygon): User AOI in EPSG 4326
        user_poly_proj3857 (shapely polygon): User AOI in EPSG 3857
    """
    wgs84 = pyproj.CRS("EPSG:4326")
    web_mercator = pyproj.CRS("EPSG:3857")
    project_gcs = pyproj.Transformer.from_crs(orig_crs, wgs84, always_xy=True).transform
    project_wm = pyproj.Transformer.from_crs(orig_crs, web_mercator, always_xy=True).transform
    user_poly_proj4326 = transform(project_gcs, poly)
    user_poly_proj3857 = transform(project_wm, poly)
    return(user_poly_proj4326, user_poly_proj3857)

def gcs_to_proj(poly):
    """
    Function for reprojecting polygon shapely object from geographic coordinates (EPSG:4326) 
    to Web Mercator (EPSG: 3857)). 
    
    Parameters:
        poly (shapely polygon): User area of interest (AOI)

    Returns:
        user_poly_proj3857 (shapely polygon): User AOI in EPSG 3857
    """
    wgs84 = pyproj.CRS("EPSG:4326")
    web_mercator = pyproj.CRS("EPSG:3857")
    project = pyproj.Transformer.from_crs(wgs84, web_mercator, always_xy=True).transform
    user_poly_proj3857 = transform(project, poly)
    return(user_poly_proj3857)

def import_shapefile_to_shapely(path):
    """
    Conversion of shapefile to shapely object.
    
    Parameters:
        path (filepath): location of shapefile on user's local file system

    Returns:
        user_AOI (shapely polygon): User AOI
    """
    shapefile_path = path
    gdf = gpd.read_file(shapefile_path)
    orig_crs = gdf.crs                   # this is the original CRS of the imported shapefile
    user_shp = gdf.loc[0, 'geometry']
    user_shp_epsg4326, user_shp_epsg3857 = proj_to_3857(user_shp, orig_crs)
    user_AOI = [[user_shp_epsg4326, user_shp_epsg3857]]
    return user_AOI
    
def handle_draw(target, action, geo_json):
    """
    Functionality to draw area of interest (AOI) on interactive ipyleaflet map.
    
    Parameters:
        extent_epsg3857 (shapely polygon): Polygon of user-defined AOI
        usgs_3dep_dataset_name (str): Name of 3DEP dataset which AOI overlaps
        resolution (float): The desired resolution of the pointcloud based on the following definition:
    """
        
    geom = dict(geo_json['geometry'])
    user_poly = shape(geom)
    user_poly_proj3857 = gcs_to_proj(user_poly)
    print('AOI is valid and has boundaries of ', user_poly_proj3857.bounds, 'Please proceed to the next cell.')
    user_AOI.append((user_poly, user_poly_proj3857))  #for various reasons, we need user AOI in GCS and EPSG 3857
    
def downsample_dem(dem):
    """
    Function for evaluating whether DEM should be downsampled prior to plotting. If dem.shape is larger than target.shape, the dem is downsampled.

    Parameters:
        dem (array): 2-D numpy array representing the dem data

    Returns: 
        down_sampled (array): Downsampled 2-D numpy array (if dimensions exceed target dimensions)
        OR
        dem (array): Original 2-D numpy array (if downsampling is not needed)
    """
    target_shape = tuple((1000,1000))   # if either dimension is larger than 1000 pixels, the dem will be downsampled
    scale_factors = [dim_target / dim_input for dim_target, dim_input in zip(target_shape, dem.shape)] 
    
    if any(factor < 1 for factor in scale_factors):
        if scale_factors[0] < 1:
            new_width = dem.rio.width * scale_factors[0]
        else:
            new_width = dem.rio.width
        if scale_factors[1] < 1:
            new_height = dem.rio.height * scale_factors[1]
        else:
            new_height = dem.rio.height

        # Downsample DTM/DSM
        down_sampled = dem.rio.reproject(dem.rio.crs, shape=(int(new_height), int(new_width)), resampling=Resampling.bilinear)
        
        return down_sampled
    
    else:
        return dem
    
def build_pdal_pipeline(extent_epsg3857, usgs_3dep_dataset_names, pc_resolution, filterNoise = False,
                        reclassify = False, savePointCloud = True, outCRS = 3857, pc_outName = 'filter_test', 
                        pc_outType = 'laz'):

    """
    Build pdal pipeline for requesting, processing, and saving point cloud data. Each processing step is a 'stage' 
    in the final pdal pipeline. Each stages is appended to the 'pointcloud_pipeline' object to produce the final pipeline.
    
    Parameters:
    extent_epsg3857 (shapely polygon): Polygon for user-defined AOI in Web Mercator projection (EPS:3857)Polygon is generated 
                            either through the 'handle_draw' methor or by inputing their own shapefile.
    usgs_3dep_dataset_names (str): List of name of the 3DEP dataset(s) that the data will be obtained. This parameter is set 
                                determined through intersecttino of the 3DEP and AOI polys.
    pc_resolution (float): The desired resolution of the pointcloud based on the following definition:
        
                        Source: https://pdal.io/stages/readers.ept.html#readers-ept
                            A point resolution limit to select, expressed as a grid cell edge length. 
                            Units correspond to resource coordinate system units. For example, 
                            for a coordinate system expressed in meters, a resolution value of 0.1 
                            will select points up to a ground resolution of 100 points per square meter.
                            The resulting resolution may not be exactly this value: the minimum possible 
                            resolution that is at least as precise as the requested resolution will be selected. 
                            Therefore the result may be a bit more precise than requested.
                            
    filterNoise (bool): Option to remove points from USGS Class 7 (Low Noise) and Class 18 (High Noise).
    reclassify (bool): Option to remove USGS classes and run SMRF to classify ground points only. Default == False.
    savePointCloud (bool): Option to save (or not) the point cloud data. If savePointCloud == False, 
           the pc_outName and pc_outType parameters are not used and can be any value.
    outCRS (int): Output coordinate reference systemt (CRS), specified by ESPG code (e.g., 3857 - Web Mercator)
    pc_outName (str): Desired name of file on user's local file system. If savePointcloud = False, 
                  pc_outName can be in value.
    pc_outType (str):  Desired file extension. Input must be either 'las' or 'laz'. If savePointcloud = False, 
                  pc_outName can be in value. If a different file type is requested,the user will get error.
    
    Returns:
        pointcloud_pipeline (dict): Dictionary of processing stages in sequential order that define PDAL pipeline.

    Raises: 
        Exception: If user passes in argument that is not 'las' or 'laz'.
    """
    
    #this is the basic pipeline which only accesses the 3DEP data
    readers = []
    for name in usgs_3dep_dataset_names:
        url = "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/{}/ept.json".format(name)
        reader = {
            "type": "readers.ept",
            "filename": str(url),
            "polygon": str(extent_epsg3857),
            "requests": 3,
            "resolution": pc_resolution
        }
        readers.append(reader)
        
    pointcloud_pipeline = {
            "pipeline":
                readers
    }
    
    if filterNoise == True:
        
        filter_stage = {
            "type":"filters.range",
            "limits":"Classification![7:7], Classification![18:18]"
        }
        
        pointcloud_pipeline['pipeline'].append(filter_stage)
    
    if reclassify == True:
        
        remove_classes_stage = {
            "type":"filters.assign",
            "value":"Classification = 0"
        }
        
        classify_ground_stage = {
            "type":"filters.smrf"
        }
        
        reclass_stage = {
            "type":"filters.range",
            "limits":"Classification[2:2]"
        }

        pointcloud_pipeline['pipeline'].append(remove_classes_stage)
        pointcloud_pipeline['pipeline'].append(classify_ground_stage)
        pointcloud_pipeline['pipeline'].append(reclass_stage)
        
    reprojection_stage = {
        "type":"filters.reprojection",
        "out_srs":"EPSG:{}".format(outCRS)
    }
    
    pointcloud_pipeline['pipeline'].append(reprojection_stage)
    
    if savePointCloud == True:
        
        if pc_outType == 'las':
            savePC_stage = {
                "type": "writers.las",
                "filename": str(pc_outName)+'.'+ str(pc_outType),
            }
        elif pc_outType == 'laz':    
            savePC_stage = {
                "type": "writers.las",
                "compression": "laszip",
                "filename": str(pc_outName)+'.'+ str(pc_outType),
            }
        else:
            raise Exception("pc_outType must be 'las' or 'laz'.")

        pointcloud_pipeline['pipeline'].append(savePC_stage)
        
    return pointcloud_pipeline

def make_DEM_pipeline(extent_epsg3857, usgs_3dep_dataset_name, pc_resolution, dem_resolution,
                      filterNoise = True, reclassify = False, savePointCloud = False, outCRS = 3857,
                      pc_outName = 'filter_test', pc_outType = 'laz', demType = 'dtm', gridMethod = 'idw', 
                      dem_outName = 'dem_test', dem_outExt = 'tif', driver = "GTiff"):
    
    """
    Build pdal pipeline for creating a digital elevation model (DEM) product from the requested point cloud data. The 
    user must specify whether a digital terrain (bare earth) model (DTM) or digital surface model (DSM) will be created, 
    the output DTM/DSM resolution, and the gridding method desired. 

    The `build_pdal_pipeline() method is used to request the data from the Amazon Web Services ept bucket, and the 
    user may define any processing steps (filtering, reclassifying, reprojecting). The user must also specify whether 
    the point cloud should be saved or not. Saving the point cloud is not necessary for the generation of the DEM. 

    Parameters:
        extent_epsg3857 (shapely polygon): User-defined AOI in Web Mercator projection (EPS:3857). Polygon is generated 
                                           either through the 'handle_draw' methor or by inputing their own shapefile.
                                           This parameter is set automatically when the user-defined AOI is chosen.
        usgs_3dep_dataset_names (list): List of name of the 3DEP dataset(s) that the data will be obtained. This parameter is set 
                                        determined through intersecttino of the 3DEP and AOI polys.
        pc_resolution (float): The desired resolution of the pointcloud based on the following definition:

                        Source: https://pdal.io/stages/readers.ept.html#readers-ept
                            A point resolution limit to select, expressed as a grid cell edge length. 
                            Units correspond to resource coordinate system units. For example, 
                            for a coordinate system expressed in meters, a resolution value of 0.1 
                            will select points up to a ground resolution of 100 points per square meter.
                            The resulting resolution may not be exactly this value: the minimum possible 
                            resolution that is at least as precise as the requested resolution will be selected. 
                            Therefore the result may be a bit more precise than requested.

        pc_outName (str): Desired name of file on user's local file system. If savePointcloud = False, 
                          pc_outName can be in value.
        pc_outType (str): Desired file extension. Input must be either 'las' or 'laz'. If savePointcloud = False, 
                          pc_outName can be in value. If a different file type is requested,the user will get error.
    
        dem_resolution (float): Desired grid size (in meters) for output raster DEM 
        filterNoise (bool): Option to remove points from USGS Class 7 (Low Noise) and Class 18 (High Noise).
        reclassify (bool): Option to remove USGS classes and run SMRF to classify ground points only. Default == False.
        savePointCloud (bool): Option to save (or not) the point cloud data. If savePointCloud == False, the pc_outName 
                               and pc_outType parameters are not used and can be any value.

        outCRS (int): Output coordinate reference systemt (CRS), specified by ESPG code (e.g., 3857 - Web Mercator)
        pc_outName (str): Desired name of file on user's local file system. If savePointcloud = False, 
                          pc_outName can be in value.
        pc_outType (str): Desired file extension. Input must be either 'las' or 'laz'. If a different file type is requested,
                    the user will get error stating "Extension must be 'las' or 'laz'". If savePointcloud = False, 
                    pc_outName can be in value.
        demType (str): Type of DEM produced. Input must 'dtm' (digital terrain model) or 'dsm' (digital surface model).
        gridMethod (str): Method used. Options are 'min', 'mean', 'max', 'idw'.
        dem_outName (str): Desired name of DEM file on user's local file system.
        dem_outExt (str): DEM file extension. Default is TIF.
        driver (str): File format. Default is GTIFF
    
    Returns:
        dem_pipeline (dict): Dictionary of processing stages in sequential order that define PDAL pipeline.
    Raises: 
        Exception: If user passes in argument that is not 'las' or 'laz'.
        Exception: If user passes in argument that is not 'dtm' or 'dsm'

    """

    dem_pipeline = build_pdal_pipeline(extent_epsg3857, usgs_3dep_dataset_name, pc_resolution,
                                              filterNoise, reclassify, savePointCloud, outCRS, pc_outName, pc_outType)
    
    if demType == 'dsm':
        dem_stage = {
                "type":"writers.gdal",
                "filename":str(dem_outName)+ '.' + str(dem_outExt),
                "gdaldriver":driver,
                "nodata":-9999,
                "output_type":gridMethod,
                "resolution":float(dem_resolution),
                "gdalopts":"COMPRESS=LZW,TILED=YES,blockxsize=256,blockysize=256,COPY_SRC_OVERVIEWS=YES"
        }
    
    elif demType == 'dtm':
        groundfilter_stage = {
                "type":"filters.range",
                "limits":"Classification[2:2]"
        }

        dem_pipeline['pipeline'].append(groundfilter_stage)

        dem_stage = {
                "type":"writers.gdal",
                "filename":str(dem_outName)+ '.' + str(dem_outExt),
                "gdaldriver":driver,
                "nodata":-9999,
                "output_type":gridMethod,
                "resolution":float(dem_resolution),
                "gdalopts":"COMPRESS=LZW,TILED=YES,blockxsize=256,blockysize=256,COPY_SRC_OVERVIEWS=YES"
        }
    
    else:
        raise Exception("demType must be 'dsm' or 'dtm'.")
        
    dem_pipeline['pipeline'].append(dem_stage)
    
    return dem_pipeline

def get_3dep_dtm(geom, pointcloud_resolution, dtm_resolution, dem_outName, outCRS):
    if Path("resources.geojson").exists() == True:
        url = 'https://raw.githubusercontent.com/hobuinc/usgs-lidar/master/boundaries/resources.geojson'
        r = requests.get(url)
    else:
        with open('resources.geojson', 'w') as f:
            f.write(r.content.decode("utf-8"))

        with open('resources.geojson', 'r') as f:
            geojsons_3DEP = json.load(f)
            
        #make pandas dataframe and create pandas.Series objects for the names, urls, and number of points for each boundary.
    with open('resources.geojson', 'r') as f:
        df = gpd.read_file(f)
        names = df['name']
        urls = df['url']
        num_points = df['count']

    #project the boundaries to EPSG 3857 (necessary for API call to AWS for 3DEP data)
    projected_geoms = []
    for geometry in df['geometry']:
            projected_geoms.append(gcs_to_proj(geometry))

    geometries_GCS = df['geometry']
    geometries_EPSG3857 = gpd.GeoSeries(projected_geoms)

    #project the boundaries to EPSG 3857 (necessary for API call to AWS for 3DEP data)
    projected_geoms = []
    for geometry in df['geometry']:
            projected_geoms.append(gcs_to_proj(geometry))

    geometries_GCS = df['geometry']
    geometries_EPSG3857 = gpd.GeoSeries(projected_geoms)

    print('Done. 3DEP polygons downloaded and projected to Web Mercator (EPSG:3857)')
    
    user_shp = geom
    user_shp_epsg4326, user_shp_epsg3857 = proj_to_3857(user_shp, orig_crs)
    user_AOI = [[user_shp_epsg4326, user_shp_epsg3857]]
    AOI_GCS = user_AOI[-1][0]
    AOI_EPSG3857 = user_AOI[-1][1]

    # Find intersecting polygons

    intersecting_polys = []

    for i,geom in enumerate(geometries_EPSG3857):
        if geom.intersects(AOI_EPSG3857):
            intersecting_polys.append((names[i], geometries_GCS[i], geometries_EPSG3857[i], urls[i], num_points[i]))
            
    wlayer_3DEP_list = []        
    usgs_3dep_datasets = []
    number_pts_est = []

    # print(intersecting_polys)
    for i, poly in enumerate(intersecting_polys):
        wlayer_3DEP_list.append(poly[1].wkt)
        usgs_3dep_datasets.append(poly[0])
        
        #estimate total points using ratio of area and point count
        number_pts_est.append((int((AOI_EPSG3857.area/poly[2].area)*(poly[4]))))

        # print(intersecting_polys)
        print(f'Your AOI at full resolution will include approximately {int(math.ceil(sum(number_pts_est)/1e6)*1e6):,} points.')
        
    #### Specify Point Cloud Resolution and Construct and Exectute PDAL Pipeline for Point Cloud Data 
    pc_pipeline = build_pdal_pipeline(AOI_EPSG3857.wkt, usgs_3dep_datasets,
                                pointcloud_resolution,
                                filterNoise = True,
                                reclassify = False,
                                savePointCloud = False, 
                                outCRS = outCRS, 
                                pc_outName = 'pointcloud_test',
                                pc_outType = 'laz')

    pc_pipeline = pdal.Pipeline(json.dumps(pc_pipeline))

    print("pc_pipeline")
    pc_pipeline.execute_streaming(chunk_size=1000000) # use this if reclassify == False 
    #pc_pipeline.execute() # use this if reclassify == True 

    # make digital terrain model

    dtm_pipeline = make_DEM_pipeline(AOI_EPSG3857.wkt, usgs_3dep_datasets, pointcloud_resolution, dtm_resolution,
                                filterNoise = True, reclassify = False, savePointCloud = False, 
                                outCRS = outCRS,
                                pc_outName = 'pointcloud_test', pc_outType = 'laz', demType = 'dtm', 
                                gridMethod='idw', 
                                dem_outName = dem_outName, 
                                dem_outExt = 'tif', driver = "GTiff")

    dtm_pipeline = pdal.Pipeline(json.dumps(dtm_pipeline))

    print('dtm_pipeline')
    dtm_pipeline.execute_streaming(chunk_size=1000000) # use this if reclassify == False 
    #dtm_pipeline.execute() # use this if reclassify == True

    # Fill NoData
    from rasterio.fill import fillnodata

    tif_file = rf'{dem_outName}.tif'
    
    with rasterio.open(tif_file) as src:
        profile = src.profile
        arr = src.read(1)
        arr_filled = fillnodata(arr, mask=src.read_masks(1), max_search_distance=10, smoothing_iterations=0)

    newtif_file = rf"{dem_outName}_filled.tif"
    
    with rasterio.open(newtif_file, 'w', **profile) as dest:
        dest.write_band(1, arr_filled)

@dask.delayed
def process_geometry(geom, index):
    sleep(1)
    get_3dep_dtm(geom, 1.0, 1.0, f'dem_tiles/tile_{index}', 32617)

shapefile_path = '/sciclone/home/jdelvecchio01/app-dd/appalachia/tiles_3dep_realigned.shp'

# user_AOI = import_shapefile_to_shapely(shapefile_path)
gdf = gpd.read_file(shapefile_path)
orig_crs = gdf.crs    

indices_to_process = list(range(len(gdf))) # or specify the indices you want to process

delayed_tasks = []
for i in indices_to_process:
    geom = gdf.iloc[i]['geometry']
    delayed_task = dask.delayed(process_geometry)(geom, i)
    delayed_tasks.append(delayed_task)

# Execute the delayed tasks in parallel
results = dask.compute(*delayed_tasks, num_workers=len(delayed_tasks))