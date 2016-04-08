from __future__ import print_function
import os
import sys
import numpy as np
import healpy as hp
from astropy import units as u
from astropy import constants as c
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz, Angle, Latitude, Longitude
import radiono as rad

######################################
### EXECUTION AND HELPER FUNCTIONS ###
######################################

def write_radec(UT, radec_file, alt_src, az_src, date_str, lat_str, lon_str, height=1051, verbose=True):
    hour = rad.std_hour(UT, verbose=False)

    lat_obs = Latitude(Angle(lat_str[:-1]))
    lon_obs = Longitude(Angle(lon_str[:-1]))

    start_time = Time(date_str)

    location = EarthLocation(lat=lat_obs, lon=lon_obs, height=height * u.m)

    altaz = SkyCoord(alt=alt_src * u.deg, az=az_src * u.deg,
                     location=location, obstime=start_time + UT * u.hr,
                     frame='altaz')
    ra = altaz.icrs.ra
    dec = altaz.icrs.dec

    with open(radec_file, 'w') as f:
        for r, d in zip(ra, dec):
            f.write('{ra} {dec}\n'.format(ra=r.value, dec=d.value))

def ion_RM(date_str, lat_str, lon_str, alt_src, az_src, verbose=True):
    year, month, day = date_str.split('T')[0].split('-')
    tec_hp, rms_hp, ion_height = rad.IONEX_data(year, month, day, verbose=verbose)

    zen_src = 90. - alt_src
    coord_lat, coord_lon, az_punct, zen_punct = rad.ipp(lat_str, lon_str, az_src, zen_src, ion_height)

    B_para = rad.B_IGRF(year, month, day,
                        coord_lat, coord_lon,
                        ion_height, az_punct, zen_punct)

    UTs = np.linspace(0, 23, num=24)

    RMs = []
    dRMs = []
    for UT in UTs:
        RM_dir = os.path.join(rad.base_path, 'RM_files/{date}'.format(date=date_str.split('T')[0]))
        if not os.path.exists(RM_dir):
            os.makedirs(RM_dir)

        hour = rad.std_hour(UT, verbose=verbose)
        radec_file = os.path.join(RM_dir, 'radec{hour}.txt'.format(hour=hour))
        write_radec(UT, radec_file, alt_src, az_src, date_str, lat_str, lon_str)

        TEC_path, RMS_TEC_path = rad.interp_space(tec_hp[UT], rms_hp[UT],
                                                  coord_lat, coord_lon,
                                                  zen_punct)

        new_file = os.path.join(RM_dir, 'IonRM{hour}.txt'.format(hour=hour))
        rad.get_results(hour, new_file, B_para, TEC_path, RMS_TEC_path)

        _, _, _, RM_add, dRM_add = np.loadtxt(new_file, unpack=True)
        RMs.append(RM_add)
        dRMs.append(dRM_add)

    return B_para, np.array(RMs), np.array(dRMs)

def maps2npz(time_str, npix, loc_str='PAPER', verbose=True):
    #I could fish around in the file read to get npix and then re-loop, but why not just be lazy sometimes
    rng = np.arange(24)
    final_TEC, final_rm, final_drm, ra, dec = np.zeros((rng.shape[0], npix)),\
                                              np.zeros((rng.shape[0], npix)),\
                                              np.zeros((rng.shape[0], npix)),\
                                              np.zeros((rng.shape[0], npix)),\
                                              np.zeros((rng.shape[0], npix))
    RM_dir = os.path.join(rad.base_path, 'RM_files/{date}'.format(date=time_str.split('T')[0]))
    for UT in rng:
        rm_file = os.path.join(RM_dir, 'IonRM{num}.txt'.format(num=rad.std_hour(UT, verbose=verbose)))
        radec_file = os.path.join(RM_dir, 'radec{num}.txt'.format(num=rad.std_hour(UT, verbose=verbose)))
        
        _, TEC, B, RM, dRM = np.loadtxt(rm_file, unpack=True)
        RA, DEC = np.loadtxt(radec_file, unpack=True)
        
        final_TEC[UT, :] = TEC
        final_rm[UT, :] = RM
        final_drm[UT, :] = dRM
        ra[UT,:] = RA
        dec[UT,:] = DEC

    f_name = ''.join((time_str.split('T')[0], '_', loc_str, '.npz'))
    npz_dir = os.path.join(rad.base_path, 'npz')
    if not os.path.exists(npz_dir):
        os.mkdir(npz_dir)
    npz_file = os.path.join(npz_dir, f_name)
    if verbose:
        print('Saving TEC, RM +/- dRM data and RA/Dec mapping to {filename}'.format(filename=npz_file))

    np.savez(npz_file, TEC=final_TEC, RM=final_rm, dRM=final_drm, RA=ra, DEC=dec)


if __name__ == '__main__':
    nside = 16
    npix = hp.nside2npix(nside)
    ipix = np.arange(npix)
    theta, phi = hp.pix2ang(nside, ipix)

    alt_src = 90. - np.degrees(np.array(theta))
    az_src = np.degrees(np.array(phi))
    
    # PAPER INFO
    lat_str = '30d43m17.5ss'
    lon_str = '21d25m41.9se'
    
    #time_str = '2012-02-13T00:00:00'

    time_part = 'T00:00:00'
    # 7 Dec 2011 to 27 Feb 2012
    dates = (('2011-12', range(6, 32)),
             ('2012-01', range(1, 32)),
             ('2012-02', range(1, 29)))
    date_strs = ('-'.join((ym, rad.std_hour(day, verbose=False))) for ym, days in dates for day in days)
    time_strs = (''.join((date_str, time_part)) for date_str in date_strs)

    for time_str in time_strs:
        B_para, RMs, dRMs = ion_RM(time_str, lat_str, lon_str, alt_src, az_src, verbose=False)
        maps2npz(time_str, npix)