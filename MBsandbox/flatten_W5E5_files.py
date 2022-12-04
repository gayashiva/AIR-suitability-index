import xarray as xr
import numpy as np
import pandas as pd
from oggm import utils

import sys
import matplotlib.pyplot as plt
import os

path='/media/share/datasets/w5e5/'
input_path='/home/bsurya/work/oggm/AIR-suitability-index/input/'
# input_path='/home/bsurya/work/oggm/AIR-suitability-index/MBsandbox/'

ds_inv = xr.open_dataset(path + 'orog_W5E5v2.0.nc')
#ds_inv = xr.open_dataset('/home/users/lschuster/glacierMIP/ASurf_WFDE5_CRU_v1.1.nc')
ds_inv = ds_inv.rename({'lat': 'latitude'})
ds_inv = ds_inv.rename({'lon': 'longitude'})
ds_inv.coords['longitude'] = np.where(ds_inv.longitude.values < 0,
                                      ds_inv.longitude.values + 360,
                                      ds_inv.longitude.values)
# (ds.coords['longitude'] + 180) % 360 - 180
ds_inv = ds_inv.sortby(ds_inv.longitude)
ds_inv.longitude.attrs['units'] = 'degrees_onlypositive'

# get the dataset where coordinates of glaciers are stored
frgi = utils.file_downloader('https://cluster.klima.uni-bremen.de/~oggm/rgi/rgi62_stats.h5')
odf = pd.read_hdf(frgi, index_col=0)

nx, ny = ds_inv.dims['longitude'], ds_inv.dims['latitude']
# Nearest neighbor lookup
cenlon_for_bins = np.where(odf['CenLon'] < -0.125,
                           odf['CenLon']+360,
                           odf['CenLon']) # just make them into 0-> 360 scheme
lon_bins = np.linspace(0, 360, nx) # np.linspace(-0.125, 359.75+0.125, nx)
# !!! attention W5E5 sorted from 90 to -90 !!!!
lat_bins = np.linspace(90, -90, ny)  #  
#lat_bins = np.linspace(90+0.125, -90-0.125, ny)
#lat_bins = np.linspace(-90, +90, ny)
odf['lon_id'] = np.digitize(cenlon_for_bins, lon_bins)-1
odf['lat_id'] = np.digitize(odf['CenLat'], lat_bins)-1
# Use unique grid points as index and compute the area per location
odf['unique_id'] = ['{:03d}_{:03d}'.format(lon, lat) for (lon, lat) in zip(odf['lon_id'], odf['lat_id'])]
mdf = odf.drop_duplicates(subset='unique_id').set_index('unique_id')
mdf['Area'] = odf.groupby('unique_id').sum()['Area']
print('Total number of glaciers: {} and number of W5E5 gridpoints with glaciers in them: {}'.format(len(odf), len(mdf)))

# this is the mask that we need to remove all non-glacierized gridpoints
mask = np.full((ny, nx), np.NaN)
mask[mdf['lat_id'], mdf['lon_id']] = 1#mdf['Area']
ds_inv['glacier_mask'] = (('latitude', 'longitude'), np.isfinite(mask))

###
# W5E5 vars required:
vars = ['hurs', 'rsds', 'tasmax', 'tasmin', 'tas', 'pr']

make_daily = False
if make_daily:
    
    for var in vars:
        try:
            # os.umask(0)
            os.mkdirs(input_path + 'flattened/tmp_{}'.format(var), 0o777)
        except:
            pass
    
    yss = [1979, 1981, 1991, 2001, 2011]
    yee = [1980, 1990, 2000, 2010, 2019]
    for var in vars:
        for ys, ye in zip(yss, yee):
            ds = xr.open_dataset(path + '{}_W5E5v2.0_{}0101-{}1231.nc'.format(var, ys, ye))

            ds = ds.rename({'lon':'longitude'}).rename({'lat':'latitude'})
            ds.coords['longitude'] = np.where(ds.longitude.values < 0,
                                              ds.longitude.values + 360,
                                              ds.longitude.values)

            ds = ds.sortby(ds.longitude)
            ds.longitude.attrs['units'] = 'degrees_onlypositive'

            # this takes too long !!!
            # ds_merged_glaciers = xr_prcp.where(ds_inv['glacier_mask'], drop = True)

            ds['ASurf'] = ds_inv['orog'] #ds_inv['ASurf']
            if ys==1979 and var =='pr':

                # as we use here only those gridpoints where glaciers are involved, need to put the mask on dsi as well!
                # dsi = ds_inv.where(ds_inv['glacier_mask'], drop = True)  # this makes out of in total 6483600 points only 116280 points!!!
                dsi = ds.isel(time=[0]).where(ds_inv['glacier_mask'], drop = True)
                # we do not want any dependency on latitude and longitude
                dsif = dsi.stack(points=('latitude', 'longitude')).reset_index(('points'))
                #dsif # so far still many points 

                # drop the non-glacierized points
                dsifs = dsif.where(np.isfinite(dsi[var].stack(points=('latitude',
                                                                      'longitude')).reset_index(('time',
                                                                                                 'points'))), drop=True)
                # I have to drop the 'time_' dimension, to be equal to the era5_land example, because the invariant file should not have any time dependence !
                dsifs = dsifs.drop_vars(var)
                dsifs = dsifs.drop('time')
                # dsifs = dsifs.drop('time_')
                dsifs.to_netcdf(input_path + 'flattened/w5e5v2.0_glacier_invariant_flat.nc')
                # dsifs.to_netcdf('w5e5v2.0_glacier_invariant_flat.nc')

                #check if gridpoint nearest to hef is right!!!
                # happened once that something went wrong here ...
                lon, lat = (10.7584, 46.8003)
                #orog = xr.open_dataset('/home/lilianschuster/Downloads/w5e5v2.0_glacier_invariant_flat.nc').ASurf
                orog = dsifs.ASurf
                c = (orog.longitude - lon)**2 + (orog.latitude - lat)**2
                surf_hef = orog.isel(points=c.argmin())
                np.testing.assert_allclose(surf_hef, 2250, rtol=0.1)
            ds = ds.drop_vars('ASurf')

            for t in ds.time.values[:]:  # ds_merged_glaciers.time.values: .sel(time=slice('1901-04','2016-12'))
                # produce a temporary file for each month
                sel_l = ds.sel(time=[t])
                # don't do the dropping twice!!!!
                #sel = sel_l.where(ds_inv['glacier_mask'], drop = True)
                sel = sel_l.where(ds_inv['glacier_mask'])
                sel = sel.stack(points=('latitude', 'longitude')).reset_index(('time', 'points'))
                sel = sel.where(np.isfinite(sel[var]), drop=True)
                sel.to_netcdf(input_path + 'flattened/tmp_{}/tmp_{}.nc'.format(var, str(t)[:10]))


###

# rename precipitation to 'pr'
# make yearly files
for var in vars:
# for var in ['hurs', 'rsds', 'tasmax', 'tasmin']:
    for y in np.arange(1979, 2020):
        print('flattened/tmp_{}/tmp_{}-*.nc'.format(var, str(y)))
        dso_y = xr.open_mfdataset(input_path + 'flattened/tmp_{}/tmp_{}-*.nc'.format(var, str(y)),
                                  concat_dim='time', combine='nested') # .rename_vars({'time_':'time'})
        dso_y.to_netcdf(input_path + 'flattened/tmp_{}/tmp2_{}.nc'.format(var, str(y)))
        dso_y.close()
    
# aggregate yearly files
# for var in ['pr', 'tas']:
for var in vars:
# for var in ['hurs', 'rsds', 'tasmax', 'tasmin']:
    dso_all2 = xr.open_mfdataset(input_path + 'flattened/tmp_{}/tmp2_*.nc'.format(var),
                        concat_dim='time', combine='nested', parallel = True) #.rename_vars({'time_':'time'})
    
    dso_all2.attrs['history'] = 'longitudes to 0 -> 360,  only glacier gridpoints chosen and flattened latitude/longitude --> points'
    dso_all2.attrs['postprocessing_date'] = str(np.datetime64('today','D'))
    # dso_all2.attrs['postprocessing_scientist'] = 'lilian.schuster@student.uibk.ac.at'
    dso_all2.attrs['postprocessing_scientist'] = 'gayashiva91@gmail.com'
    dso_all2.to_netcdf(input_path + 'flattened/w5e5v2.0_{}_global_daily_flat_glaciers_1979_2019.nc'.format(var))
        
# make monthly files 
# for var in ['pr', 'tas']:
for var in vars:
# for var in ['hurs', 'rsds', 'tasmax', 'tasmin']:

    pathi= 'flattened/w5e5v2.0_{}_global_daily_flat_glaciers_1979_2019.nc'.format(var)
    ds = xr.open_dataset(input_path + pathi)


    ds_monthly = ds.resample(time='MS', keep_attrs=True).mean(keep_attrs=True)

    # ds_monthly.attrs['postprocessing_scientist'] = 'lilian.schuster@student.uibk.ac.at'
    ds_monthly.attrs['postprocessing_scientist'] = 'gayashiva91@gmail.com'
    ds_monthly.attrs['postprocessing_actions'] =  ("using xarray: ds_monthly = ds.resample(time='MS', keep_attrs=True).mean(keep_attrs=True)\n"
                                                                      "ds_monthly.to_netcdf()\n")

    ds_monthly.to_netcdf(input_path + 'flattened/w5e5v2.0_{}_global_monthly_flat_glaciers_1979_2019.nc'.format(var))
    
    if var == 'tas':
        # also compute monthly daily std:

        ds_tas_daily_std = ds.resample(time='MS', keep_attrs=True).std(keep_attrs=True)
        ds_tas_daily_std = ds_tas_daily_std.rename_vars(dict(tas='tas_std'))
        # now have to change variable tas to tas_std and its attributes 
        ds_tas_daily_std.tas_std.attrs['standard_name'] = 'air_temperature_daily_std'
        ds_tas_daily_std.tas_std.attrs['long_name'] = 'Near-Surface Air Temperature daily standard deviation'
        ds_tas_daily_std.attrs['postprocessing_date'] = str(np.datetime64('today','D'))
        # ds_tas_daily_std.attrs['postprocessing_scientist'] = 'lilian.schuster@student.uibk.ac.at'
        ds_tas_daily_std.attrs['postprocessing_scientist'] = 'gayashiva91@gmail.com'
        ds_tas_daily_std.attrs['postprocessing_actions'] =  ("using xarray: \n"
                                                                      "ds_tas_daily_std = ds.resample(time='MS', keep_attrs=True).std(keep_attrs=True)\n"
                                                                       "ds_tas_daily_std = ds_tas_daily_std.rename_vars(dict(tas='tas_std'))\n"
                                                                       "ds_tas_daily_std.tas_std.attrs['standard_name'] = 'air_temperature_daily_std'\n"
                                                                       "ds_tas_daily_std.tas_std.attrs['long_name'] = 'Near-Surface Air Temperature daily standard deviation'\n"
                                                                      "ds_tas_daily_std.to_netcdf(...)\n")
        
        ds_tas_daily_std.to_netcdf(input_path + 'flattened/w5e5v2.0_tas_std_global_monthly_flat_glaciers_1979_2019.nc')
        
        
        
#import os
import glob
for var in vars:
# for var in ['pr']:
# for var in ['hurs', 'rsds', 'tasmax', 'tasmin']:
    files = glob.glob(input_path + 'flattened/tmp_{}/tmp*'.format(var))
    for f in files:
        os.remove(f)

