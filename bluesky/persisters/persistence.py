__author__ = "Tobias Schmidt"

from datetime import timedelta
import logging
import copy

from bluesky.config import Config

class Persistence(object):
    """ BSF's Persistence Model 

    Persistence was copied from BlueSky Framework, and subsequently modified
    TODO: acknowledge original authors (STI?)
    """

    def run(self, fires_manager):
        n_created = self._fill_missing_fires(fires_manager)

        logging.info('Persistence model created %d new fire records' % n_created)

    def _fill_missing_fires(self, fires_manager):
        """Fill-in (persist) that do not extend to the end of the emissions period"""
        n_created = 0
        first_hour, num_hours = self._get_time(fires_manager)
        last_hour = first_hour + timedelta(hours=num_hours)
        # last_hour = Config().get('filter','time','end')
        fire_events = {}

        # This is to ensure we are not double counting any fires.
        # Future fires that already exist (have an event_id) will
        # not have past data persisted overtop of the existing data
        # for fire in fires_manager.fires:
        #     event = fire["event_of"]["id"]
        #     start = fire["activity"][0]["active_areas"][0]["start"]
        #     if event not in fire_events:
        #         fire_events[event] = [start]
        #     else:
        #         fire_events[event].append(start)



        for fire in fires_manager.fires:
            with fires_manager.fire_failure_handler(fire):
                aa = fire["activity"]
                event = fire["event_of"]["id"]
                if len(aa) != 1:
                    raise ValueError("Each fire must have only 1 activity object when running persistence")
                if len(aa[0]["active_areas"]) != 1:
                    raise ValueError("Each fire must have only 1 active area when running persistence")
                start = aa[0]["active_areas"][0]["start"] + timedelta(days=1)
                end = aa[0]["active_areas"][0]["end"] + timedelta(days=1)

                while start <= last_hour:
                    # if start in fire_events[event]:
                    #     break
                    n_created += 1
                    new_aa = copy.deepcopy(aa[0])
                    new_aa["active_areas"][0]["start"] = start
                    new_aa["active_areas"][0]["end"] = end
                    fire["activity"].append(new_aa)
                    start += timedelta(days=1)
                    end += timedelta(days=1)

        # self._remove_unused_fires(fires_manager,first_hour,last_hour)
        return n_created
    
    # Clear out the fires in the fires_manager that will never
    # contribute to the dispersion anwyays
    # TODO: Make this more efficient
    def _remove_unused_fires(self,fires_manager,first_hour,last_hour):
        fires_for_deletion = []

        for fire in fires_manager.fires:
            with fires_manager.fire_failure_handler(fire):
                activity_for_deletion = []
                i = 0
                for a in fire["activity"]:
                    start = a["active_areas"][0]["start"]
                    end = a["active_areas"][0]["end"]
                    if end <= first_hour or start >= last_hour:
                        activity_for_deletion.append(i)
                    i = i + 1
                if len(activity_for_deletion) == len(fire["activity"]):
                    fires_for_deletion.append(fire)
                else:
                    for j in activity_for_deletion:
                        fire["activity"].pop(j)
        
        for fire in fires_for_deletion:
            fires_manager.remove_fire(fire)

    def _get_time(self, fires_manager):
        SECONDS_PER_HOUR = 3600
        start = Config().get('dispersion', 'start')
        num_hours = Config().get('dispersion', 'num_hours')

        if not start or num_hours is None:
            s = fires_manager.earliest_start # needed for 'start' and 'num_hours'
            if not s:
                raise ValueError("Unable to determine dispersion 'start'")
            if not start:
                start = s

            if not num_hours and start == s:
                e = fires_manager.latest_end # needed only for num_hours
                if e and e > s:
                    num_hours = int((e - s).total_seconds() / SECONDS_PER_HOUR)
            if not num_hours:
                raise ValueError("Unable to determine dispersion 'num_hours'")

        logging.debug("Dispersion window: %s for %s hours", start, num_hours)
        return start, num_hours
