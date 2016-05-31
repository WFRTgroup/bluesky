"""bluesky.visualizers.disersion"""

__author__ = "Joel Dubowy"

__all__ = [
    'HysplitVisualizer'
]
__version__ = "0.1.0"

import copy
import csv
import datetime
import json
import logging
import os
from collections import namedtuple

from pyairfire import osutils
from pyairfire.datetime import parsing as datetime_parsing

from blueskykml import (
    makedispersionkml, makeaquiptdispersionkml,
    configuration as blueskykml_configuration,
    smokedispersionkml, __version__ as blueskykml_version
)
from bluesky import configuration
from bluesky.exceptions import BlueSkyConfigurationError

###
### HYSPLIT Dispersion Visualization
###

ARGS = [
    "output_directory", "configfile",
    "prettykml", "verbose", "config_options",
    "inputfile","fire_locations_csv",
    "fire_events_csv", "smoke_dispersion_kmz_file",
    "fire_kmz_file","layer"
]
BlueskyKmlArgs = namedtuple('BlueskyKmlArgs', ARGS)

DEFAULT_FILENAMES = {
    "fire_locations_csv": 'fire_locations.csv',
    "fire_events_csv": 'fire_events.csv',
    "smoke_dispersion_kmz": 'smoke_dispersion.kmz',
    "fire_kmz": 'fire_locations.kmz',
}

BLUESKYKML_DATE_FORMAT = smokedispersionkml.FireData.date_time_format

# as of blueskykml v0.2.5, this list is:
#  'pm25', 'pm10', 'co', 'co2', 'ch4', 'nox', 'nh3', 'so2', 'voc'
BLUESKYKML_SPECIES_LIST = [s.upper() for s in smokedispersionkml.FireData.emission_fields]
if 'NOX' in BLUESKYKML_SPECIES_LIST:
    BLUESKYKML_SPECIES_LIST.remove('NOX')
    BLUESKYKML_SPECIES_LIST.append('NOx')

##
## Functions for extracting fire *location * information to write to csv files
##
## Note: The growth object (arg 'g') is ignored in most of these methods.
##  It's only needed for the start time and area calculation
##

def _pick_representative_fuelbed(fire, g):
    sorted_fuelbeds = sorted(fire.get('fuelbeds', []),
        key=lambda fb: fb['pct'], reverse=True)
    if sorted_fuelbeds:
        return sorted_fuelbeds[0]['fccs_id']

def _get_heat(fire, g):
    if fire.get('fuelbeds'):
        heat = [fb.get('heat', {}).get('total') for fb in fire['fuelbeds']]
        # non-None value will be returned if species is defined for all fuelbeds
        if not any([v is None for v in heat]):
            # heat is array of arrays
            return sum([sum(h) for h in heat])

def _get_emissions_species(species):
    def f(fire, g):
        if fire.get('fuelbeds'):
            species_array = [
                fb.get('emissions', {}).get('total', {}).get(species)
                    for fb in fire['fuelbeds']
            ]
            # non-None value will be returned if species is defined for all fuelbeds
            if not any([v is None for v in species_array]):
                return sum([sum(a) for a in species_array])
    return f

# Fire locations csv columns from BSF:
#  id,event_id,latitude,longitude,type,area,date_time,elevation,slope,
#  state,county,country,fips,scc,fuel_1hr,fuel_10hr,fuel_100hr,fuel_1khr,
#  fuel_10khr,fuel_gt10khr,shrub,grass,rot,duff,litter,moisture_1hr,
#  moisture_10hr,moisture_100hr,moisture_1khr,moisture_live,moisture_duff,
#  consumption_flaming,consumption_smoldering,consumption_residual,
#  consumption_duff,min_wind,max_wind,min_wind_aloft,max_wind_aloft,
#  min_humid,max_humid,min_temp,max_temp,min_temp_hour,max_temp_hour,
#  sunrise_hour,sunset_hour,snow_month,rain_days,heat,pm25,pm10,co,co2,
#  ch4,nox,nh3,so2,voc,canopy,event_url,fccs_number,owner,sf_event_guid,
#  sf_server,sf_stream_name,timezone,veg
FIRE_LOCATIONS_CSV_FIELDS = [
    ('id', lambda f, g: f.id),
    # Note: We're keeping the 'type' field consistent with the csv files
    #   generated by smartfire, which use 'RX' and 'WF'
    ('type', lambda f, g: 'RX' if f.type == 'rx' else 'WF'),
    ('latitude', lambda f, g: f.latitude),
    ('longitude', lambda f, g: f.longitude),
    ('area', lambda f, g: float(f.location.get('area') * g['pct']) / 100.0),
    ('date_time', lambda f, g: datetime_parsing.parse(g['start']).strftime(BLUESKYKML_DATE_FORMAT)),
    ('event_name', lambda f, g: f.get('event_of', {}).get('name')),
    ('event_guid', lambda f, g: f.get('event_of', {}).get('id')),
    ('fccs_number', _pick_representative_fuelbed),
    # TODO: Add other fields if users want them
    # TODO: add other sf2 fields (which we're now ingesting)
    # TDOO: add 'VEG'? (Note: sf2 has 'veg' field, which we're *not* ingesting,
    #   since it seems to be a fuelbed discription which is probably for
    #   the one fccs id in the sf2 feed. This single fccs id and its description
    #   don't necesasrily represent the entire fire area, which could have
    #   multiple fuelbeds, so ingestion ignores it.  we could set 'VEG' to
    #   a concatenation of the fuelbeds or the one one making up the largest
    #   fraction of the fire.)
    ('heat', _get_heat)
] + [(s.lower(), _get_emissions_species(s)) for s in BLUESKYKML_SPECIES_LIST]
"""List of fire location csv fields, with function to extract from fire object"""

##
## Functions for extracting fire *event* information to write to csv files
##

def _assign_event_name(event, fire, new_fire):
    name = fire.get('event_of', {}).get('name')
    if name:
        if event.get('name') and name != event['name']:
            logging.warn("Fire {} event name conflict: '{}' != '{}'".format(
                fire.id, name, event['name']))
        event['name'] = name

def _update_event_area(event, fire, new_fire):
    if not fire.get('location', {}).get('area'):
        raise ValueError("Fire {} lacks area".format(fire.get('id')))
    return event.get('total_area', 0.0) + fire['location']['area']

def _update_total_heat(event, fire, new_fire):
    if 'total_heat' in event and event['total_heat'] is None:
        # previous fire didn't have heat defined; abort so
        # that we don't end up with misleading partial heat
        return
    logging.debug("total fire heat: %s", new_fire.get('heat'))
    if new_fire.get('heat'):
        return event.get('total_heat', 0.0) + new_fire['heat']

def _update_total_emissions_species(species):
    key = 'total_{}'.format(species)
    def f(event, fire, new_fire):
        if key in event and event[key] is None:
            # previous fire didn't have this emissions value defined; abort so
            # that we don't end up with misleading partial total
            return

        if new_fire.get(species):
            return event.get(key, 0.0) + new_fire[species]
    return f

# Fire events csv columns from BSF:
#  id,event_name,total_area,total_heat,total_pm25,total_pm10,total_pm,
#  total_co,total_co2,total_ch4,total_nmhc,total_nox,total_nh3,total_so2,
#  total_voc,total_bc,total_h2,total_nmoc,total_no,total_no2,total_oc,
#  total_tpc,total_tpm
FIRE_EVENTS_CSV_FIELDS = [
    ('event_name', _assign_event_name),
    ('total_heat', _update_total_heat),
    ('total_area', _update_event_area),
    ('total_nmhc', _update_total_emissions_species('nmhc'))
] + [
    ('total_{}'.format(s.lower()), _update_total_emissions_species(s.lower()))
        for s in BLUESKYKML_SPECIES_LIST
]
"""List of fire event csv fields, with function to extract from fire object
and aggregate.  Note that this list lacks 'id', which is the first column.
"""

##
## Visualizer class
##

class HysplitVisualizer(object):
    def __init__(self, hysplit_output_info, fires, run_id, **config):
        self._hysplit_output_info = hysplit_output_info
        self._fires = fires
        self._run_id = run_id
        self._config = config

    def run(self):
        hysplit_output_directory = self._hysplit_output_info.get('directory')
        if not hysplit_output_directory:
            raise ValueError("hysplit output directory must be defined")
        if not os.path.isdir(hysplit_output_directory):
            raise RuntimeError("hysplit output directory {} is not valid".format(
                hysplit_output_directory))

        hysplit_output_file = self._hysplit_output_info.get('grid_filename')
        if not hysplit_output_file:
            raise ValueError("hysplit output file must be defined")
        hysplit_output_file = os.path.join(hysplit_output_directory, hysplit_output_file)
        if not os.path.isfile(hysplit_output_file):
            raise RuntimeError("hysplit output file {} does not exist".format(
                hysplit_output_file))

        if self._config.get('dest_dir'):
            output_directory = os.path.join(self._config['dest_dir'], self._run_id)
        else:
            output_directory =  hysplit_output_directory
        data_dir = os.path.join(output_directory, self._config.get('data_dir') or '')
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        files = {
            'fire_locations_csv': self._get_file_name(
                data_dir, 'fire_locations_csv'),
            'fire_events_csv': self._get_file_name(
                data_dir, 'fire_events_csv'),
            'smoke_dispersion_kmz': self._get_file_name(
                output_directory, 'smoke_dispersion_kmz'),
            'fire_kmz': self._get_file_name(
                output_directory, 'fire_kmz')
        }

        self._generate_fire_csv_files(files['fire_locations_csv']['pathname'],
            files['fire_events_csv']['pathname'])

        self._generate_summary_json(output_directory)

        config_options = self._get_config_options(output_directory)

        layer = self._config.get('layer')
        args = BlueskyKmlArgs(
            output_directory=str(output_directory),
            configfile=None, # TODO: allow this to be configurable?
            prettykml=self._config.get('prettykml'),
            # in blueskykml, if verbose is True, then logging level will be set
            # DEBUG; otherwise, logging level is left as is.  bsp already takes
            # care of setting log level, so setting verbose to False will let
            # blueskykml inherit logging level
            verbose=False,
            config_options=config_options,
            inputfile=str(hysplit_output_file),
            fire_locations_csv=str(files['fire_locations_csv']['pathname']),
            fire_events_csv=str(files['fire_events_csv']['pathname']),
            smoke_dispersion_kmz_file=str(files['smoke_dispersion_kmz']['pathname']),
            fire_kmz_file=str(files['fire_kmz']['pathname']),
            # even though 'layer' is an integer index, the option must be of type
            # string or else config.get(section, "LAYER") will fail with error:
            #  > TypeError: argument of type 'int' is not iterable
            # it will be cast to int if specified
            layer=str(layer) if layer else None
        )

        try:
            # Note: using create_working_dir effectively marks any
            #  intermediate outputs for cleanup
            with osutils.create_working_dir() as wdir:
                if self._config.get('is_aquipt'):
                    makeaquiptdispersionkml.main(args)
                else:
                    makedispersionkml.main(args)
        except blueskykml_configuration.ConfigurationError, e:
            raise BlueSkyConfigurationError(".....")

        return {
            'blueskykml_version': blueskykml_version,
            "output": {
                "directory": output_directory,
                "hysplit_output_file": hysplit_output_file,
                "smoke_dispersion_kmz_filename": files['smoke_dispersion_kmz']['name'],
                "fire_kmz_filename": files['fire_kmz']['name'],
                "fire_locations_csv_filename": files['fire_locations_csv']['name'],
                "fire_events_csv_filename": files['fire_events_csv']['name']
                # TODO: add location of image files, etc.
            }
        }

    def _get_file_name(self, directory, f):
        name = self._config.get('{}_filename'.format(f), DEFAULT_FILENAMES[f])
        return {
            "name": name,
            "pathname": os.path.join(directory, name)
        }

    def _collect_csv_fields(self):
        # As we iterate through fires, collecting necessary fields, collect
        # events information as well
        fires = []
        events = {}
        for fire in self._fires:
            for g in fire.growth:
                fires.append({k: l(fire, g) or '' for k, l in FIRE_LOCATIONS_CSV_FIELDS})
            event_id = fire.get('event_of', {}).get('id')
            if event_id:
                events[event_id] = events.get(event_id, {})
                for k, l in FIRE_EVENTS_CSV_FIELDS:
                    events[event_id][k] = l(events[event_id], fire, fires[-1])
        logging.debug("events: %s", events)
        return fires, events

    def _generate_fire_csv_files(self, fire_locations_csv_pathname,
            fire_events_csv_pathname):
        """Generates fire locations and events csvs

        These are used by blueskykml, but are also used by end users.
        If it weren't for end users wanting the files, we might want to
        consider refactoring blueskykml to accept the fire data in
        memory (in the call to makedispersionkml.main(args)) rather
        reading it from file.
        """
        # TODO: Make sure that the files don't already exists
        # TODO: look in blueskykml code to see what it uses from the two csvs

        fires, events = self._collect_csv_fields()
        with open(fire_locations_csv_pathname, 'w') as _f:
            f = csv.writer(_f)
            f.writerow([k for k, l in FIRE_LOCATIONS_CSV_FIELDS])
            for fire in fires:
                f.writerow([str(fire[k] or '') for k, l in FIRE_LOCATIONS_CSV_FIELDS])

        with open(fire_events_csv_pathname, 'w') as _f:
            f = csv.writer(_f)
            f.writerow(['id'] + [k for k, l in FIRE_EVENTS_CSV_FIELDS])
            for e_id, event in events.items():
                f.writerow([e_id] +
                    [str(event[k] or '') for k, l in FIRE_EVENTS_CSV_FIELDS])

    def _generate_summary_json(self, output_directory):
        """Creates summary.json (like BSF's) if configured to do so
        """
        if self._config.get('create_summary_json'):
            grid_params = self._hysplit_output_info.get("grid_parameters", {})
            d_from = d_to = None
            try:
                d_from = datetime_parsing.parse(
                    self._hysplit_output_info.get("start_time"))
                d_to = d_from + datetime.timedelta(
                    hours=self._hysplit_output_info.get("num_hours"))
            except:
                pass

            contents = {
                 "output_version": "1.0.0",
                 # TODO: populate with real values
                 "dispersion_period": {
                    "from": d_from and d_from.strftime("%Y%m%d %HZ"),
                    "to": d_to and d_to.strftime("%Y%m%d %HZ")
                },
                 "width_longitude": grid_params.get("width_longitude"),
                 "height_latitude": grid_params.get("height_latitude"),
                 "center_latitude": grid_params.get("center_latitude"),
                 "center_longitude":  grid_params.get("center_longitude"),
                 "model_configuration": "HYSPLIT"
            }

            contents_json = json.dumps(contents)
            logging.debug("generating summary.json: %s", contents_json)
            with open(os.path.join(output_directory, 'summary.json'), 'w') as f:
                f.write(contents_json)

    DEFAULT_FIRE_EVENT_ICON = "http://maps.google.com/mapfiles/ms/micons/firedept.png"
    def _get_config_options(self, output_directory):
        """Creates config options dict to be pass into BlueSkyKml

        This method supports specifying old BSF / blueskykml ini settings
        under the blueskykml_config config key, which (if defined) is expected
        to contain nested dicts (each dict representing a config section).
        e.g.

            "visualization": {
                "target": "dispersion",
                "hysplit": {
                    "dest_dir": "/sdf/sdf/",
                    ...,
                    "blueskykml_config": {
                        "SmokeDispersionKMLInput": {
                            "FIRE_EVENT_ICON"  : "http://maps.google.com/mapfiles/ms/micons/firedept.png"
                        }
                        ...
                    }
                }
            }

         The config_options dict returned by this method is initialized with
         whatever is specified under blueskykml_config.  Then, specific
         config options are set if not already defined.

          - 'SmokeDispersionKMLInput' > 'FIRE_EVENT_ICON' -- set to
            "http://maps.google.com/mapfiles/ms/micons/firedept.png"
          - 'DispersionGridOutput' > 'OUTPUT_DIR'
        """
        config_options = copy.deepcopy(self._config.get('blueskykml_config') or {})

        # TODO: should we be using google's icon as the default?
        # Use google's fire icon instead of BlueSkyKml's built-in icon
        # (if an alternative isn't already specified)
        if configuration.get_config_value(config_options,
                'SmokeDispersionKMLInput', 'FIRE_EVENT_ICON') is None:
            configuration.set_config_value(config_options,
                self.DEFAULT_FIRE_EVENT_ICON,
                'SmokeDispersionKMLInput', 'FIRE_EVENT_ICON')

        # set output directory if not already specified
        if configuration.get_config_value(config_options,
                'DispersionGridOutput', 'OUTPUT_DIR') is None:
            images_dir = str(os.path.join(output_directory,
                self._config.get('images_dir') or ''))
            configuration.set_config_value(config_options, images_dir,
                'DispersionGridOutput', 'OUTPUT_DIR')

        return config_options
