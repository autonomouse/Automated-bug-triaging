#! /usr/bin/env python2

import os
import bisect
import time
import yaml
import parsedatetime as pdt
from dateutil.parser import parse
from datetime import datetime
from jenkinsapi.custom_exceptions import *


class Common(object):
    """ Common methods
    """

    def add_to_yaml(self, matching_bugs, build_status, existing_dict):
        # TODO: Change this to take in the  pipeline and tc_host
        """
        Creates a yaml dict and populates with data in the right format and
        merges with existing yaml dict.

        """
        # Make dict
        pipeline_dict = {}
        yaml_dict = {}

        if matching_bugs != {}:
            pipeline_dict = {self.pipeline: {'status': build_status,
                                             'bugs': matching_bugs}}
            if hasattr(self, 'build_number'):
                pipeline_dict[self.pipeline]['build'] = self.build_number

            pipeline_dict[self.pipeline]['link to test-catalog'] = \
                self.cli.tc_host.replace('api', "pipeline/" + self.pipeline)
            pipeline_dict[self.pipeline]['Crude-Analysis timestamp'] = \
                datetime.utcnow().strftime('%Y-%B-%d %H:%M:%S.%f')
            try:
                pipeline_dict[self.pipeline]['Jenkins timestamp'] = \
                    self.bsnode['timestamp']
            except:
                pass

        # Merge with existing dict:
        if existing_dict:
            if 'pipeline' in existing_dict:
                yaml_dict['pipeline'] = \
                    self.join_dicts(existing_dict['pipeline'], pipeline_dict)
            else:
                yaml_dict['pipeline'] = \
                    self.join_dicts(existing_dict, pipeline_dict)
        else:
            yaml_dict['pipeline'] = pipeline_dict
        return yaml_dict

    def join_dicts(self, old_dict, new_dict):
        """ Merge matching_bugs dictionaries. """
        earlier_items = list(old_dict.items())
        current_items = list(new_dict.items())
        return dict(earlier_items + current_items)

    def calculate_progress(self, current_position, prog_list,
                           percentage_to_report_at=None):
        """
            Calculates and returns a percentage to notify user of progress
            completion based on the number of entries in prog_list, or
            prog_list itself if it is an integer.

        """
        if type(prog_list) not in [list, set, dict]:
            total = int(prog_list)
        else:
            total = len(prog_list)

        if not percentage_to_report_at:
            if total > 350:
                report_at = range(5, 100, 5)  # Notify every 5 percent
            elif total > 150:
                report_at = range(10, 100, 10)  # Notify every 10 percent
            elif total > 50:
                report_at = range(25, 100, 25)  # Notify every 25 percent
            else:
                report_at = [50]  # Notify at 50 percent
        else:
            report_at = range(percentage_to_report_at, 100,
                              percentage_to_report_at)

        progress = [round((pc / 100.0) * total) for pc in report_at]

        if current_position in progress:
            return str(report_at[progress.index(current_position)])

    def write_output_yaml(self, output_dir, filename, yaml_dict, verbose=True):
        """
        """
        file_path = os.path.join(output_dir, filename)
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)
        with open(file_path, 'w') as outfile:
            outfile.write(yaml.safe_dump(yaml_dict, default_flow_style=False))
        if verbose:
            self.cli.LOG.info("{} written to {}.".format(filename,
                              os.path.abspath(output_dir)))

    def get_yaml(self, file_location, yaml_dict):
        return self.get_from_file(file_location, yaml_dict, ftype='yaml')

    def get_txt(self, file_location, yaml_dict):
        return self.get_from_file(file_location, yaml_dict, ftype='text')

    def get_from_file(self, file_location, yaml_dict, ftype='yaml'):
        try:
            with open(file_location, "r") as f:
                if ftype == 'yaml':
                    return (yaml.load(f), yaml_dict)
                else:
                    return (f.read(), yaml_dict)
        except IOError as e:
            fname = file_location.split('/')[-1]
            self.cli.LOG.error("%s: %s is not in artifacts folder (%s)"
                               % (self.pipeline, fname, e[1]))
            msg = fname + ' MISSING'
            yaml_dict = self.non_db_bug(special_cases.bug_dict[fname],
                                        yaml_dict, msg)
            return (None, yaml_dict)

    def mkdir(self, directory):
        """ Make a directory, check and throw an error if failed. """
        if not os.path.isdir(directory):
            try:
                os.makedirs(directory)
            except OSError:
                if not os.path.isdir(directory):
                    raise

    def log_pipelines(self):
        """ Record which pipelines were processed in a yaml. """

        if self.cli.logpipelines:
            file_path = os.path.join(self.cli.reportdir,
                                     'pipelines_processed.yaml')
            open(file_path, 'a').close()  # Create file if doesn't exist yet
            with open(file_path, 'r+') as pp_file:
                existing_content = pp_file.read()
                pp_file.seek(0, 0)  # Put at beginning of file
                pp_file.write("\n" + str(datetime.now())
                              + "\n--------------------------\n")
                pp_file.write(" ".join(self.pipeline_ids))
                pp_file.write("\n" + existing_content)
                info_msg = "All processed pipelines recorded to {0}"
                self.cli.LOG.info(info_msg.format(file_path))

    def dictator(self, dictionary, dkey, dvalue):
        """ Adds dvalue to list in a given dictionary (self.oil_df/oil_nodes).
            Assumes that dictionary will be self.oil_df, self.oil_nodes, etc so
            nothing is returned.

        """

        if dkey not in dictionary:
            dictionary[dkey] = []
        dictionary[dkey].append(dvalue)

    def date_parse(self, string):
        """Use two different strtotime functions to return a datetime
        object when possible.
        """
        try:
            return pytz.utc.localize(parse(string))
        except:
            pass

        try:
            val = pdt.Calendar(pdt.Constants(usePyICU=False)).parse(string)
            if val[1] > 0:  # only do strict matching
                return pytz.utc.localize(datetime(*val[0][:6]))
        except:
            pass
        verr = "Date format {} not understood, try 2014-02-12"
        raise ValueError(verr.format(string))

    def find_build_newer_than(self, builds, start):
        """
        From oil-stats.

        Assumes builds have been sorted.
        """

        # pre calculate key list
        keys = [r['timestamp'] for r in builds]

        # make a micro timestamp from input
        start_ts = int(time.mktime(start.timetuple())) * 1000

        # find leftmost item greater than or equal to start
        i = bisect.bisect_left(keys, start_ts)
        if i != len(keys):
            return i

        print("No job newer than %s" % (start))
        return None

    def is_running(self, build):
        """
        From oil-stats.

        Jenkins job helper.

        """
        return build['duration'] == 0

    def is_good(self, build):
        """
        From oil-stats.

        Jenkins job helper.

        """
        return (not is_running(build) and build['result'] == 'SUCCESS')

    def time_format(self, time):
        """
        From oil-stats.

        Jenkins job helper.

        Use strftime to convert to spaceless string

        param time: datetime object
        """
        return time.strftime('%Y%m%d-%H%M%S.%f')
