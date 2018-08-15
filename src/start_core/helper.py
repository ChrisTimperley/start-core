__all__ = ['DEVNULL', 'observe', 'distance', 'get_location_metres']

import math
import os
import subprocess

import dronekit
from pymavlink import mavutil

try:
    DEVNULL = subprocess.DEVNULL
except AttributeError:
    DEVNULL = open(os.devnull, 'w')


def observe(vehicle):
    """
    Produces a snapshot of the current state of the vehicle.
    """
    snap = {
        'is_armable': vehicle.is_armable,
        'armed': vehicle.armed,
        'mode': vehicle.mode.name,
        'groundspeed': vehicle.groundspeed,
        'heading': vehicle.heading,
        'lat': vehicle.location.global_frame.lat,
        'lon': vehicle.location.global_frame.lon,
        'alt': vehicle.location.global_frame.alt
    }
    return snap


def distance(loc_x, loc_y):
    """
    Returns the ground distance in metres between two `LocationGlobal` or `LocationGlobalRelative` objects.

    This method is an approximation, and will not be accurate over large distances and close to the
    earth's poles. It comes from the ArduPilot test code:
    https://github.com/diydrones/ardupilot/blob/master/Tools/autotest/common.py
    """
    d_lat = loc_y.lat - loc_x.lat
    d_long = loc_y.lon - loc_x.lon
    return math.sqrt((d_lat*d_lat) + (d_long*d_long)) * 1.113195e5


def get_location_metres(original_location, dNorth, dEast):
    """
    Returns a LocationGlobal object containing the latitude/longitude `dNorth` and `dEast` metres from the 
    specified `original_location`. The returned Location has the same `alt` value
    as `original_location`.

    The function is useful when you want to move the vehicle around specifying locations relative to 
    the current vehicle position.
    The algorithm is relatively accurate over small distances (10m within 1km) except close to the poles.
    For more information see:
    http://gis.stackexchange.com/questions/2951/algorithm-for-offsetting-a-latitude-longitude-by-some-amount-of-meters
    """
    earth_radius=6378137.0
    dLat = dNorth/earth_radius
    dLon = dEast/(earth_radius*math.cos(math.pi*original_location.lat/180))

    newlat = original_location.lat + (dLat * 180/math.pi)
    newlon = original_location.lon + (dLon * 180/math.pi)
    return dronekit.LocationGlobal(newlat, newlon,original_location.alt)
