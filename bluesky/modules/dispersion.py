"""bluesky.modules.dispersion

If running hysplit dispersion, you'll need to obtain hysplit from NOAA.It is
expected to reside in a directory in the search path. (This module prevents
configuring relative or absolute paths to hysplit, to eliminiate security
vulnerabilities when invoked by web service request.) To obtain hysplit, Go to
NOAA's [hysplit distribution page](http://ready.arl.noaa.gov/HYSPLIT.php).
"""

__author__      = "Joel Dubowy"
__copyright__   = "Copyright 2015, AirFire, PNW, USFS"

import consume
import logging

__all__ = [
    'run'
]

__version__ = "0.1.0"

def run(fires_manager, config=None):
    """Runs dispersion module

    Args:
     - fires_manager -- bluesky.models.fires.FiresManager object
    Kwargs:
     - config -- optional configparser object
    """
    raise NotImplementedError("dispersion not yet implemented")
