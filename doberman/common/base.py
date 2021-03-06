#! /usr/bin/env python2

import os
import pytz
import bisect
import time
import yaml
import re
import shutil
import parsedatetime as pdt
from copy import deepcopy
from dateutil.parser import parse
from datetime import datetime
from jenkinsapi.custom_exceptions import *
from collections import OrderedDict


class DobermanBase(object):
    """ Common methods"""

    def add_to_yaml(self, matching_bugs, existing_dict,
                    build_status='Unknown'):
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
        """Merge matching_bugs dictionaries."""
        bad_dicts = [None, {}, '']
        if old_dict in bad_dicts and new_dict in bad_dicts:
            return {}
        elif old_dict in bad_dicts:
            return new_dict
        elif new_dict in bad_dicts:
            return old_dict
        combined_dict = deepcopy(old_dict)
        for new_pipeline, new_pl_dict in new_dict.items():
            if new_pipeline not in combined_dict:
                combined_dict[new_pipeline] = new_pl_dict
            else:
                combined_dict[new_pipeline] = dict(
                    old_dict[new_pipeline].items() + new_pl_dict.items())
        return combined_dict

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

    def build_pl_ids_and_check(self, ci_server, buildtracker,
                               ts_format='%a %d %b %Y %H:%M:%S'):
        self.pipeline_ids = []
        self.ids = self.cli.ids

        if self.cli.offline_mode:
            self.cli.LOG.info(" *** Offline mode *** ")
            build_numbers = buildtracker.get_pipelines_from_paabn()
            self.ids = build_numbers.keys()

        elif self.cli.use_deploy:
            # If using build numbers instead of pipelines, get pipeline:
            msg = "Looking up pipeline ids for the following jenkins "
            msg += "pipeline_deploy build numbers: %s"
            self.cli.LOG.info(msg % ", ".join([str(i) for i in self.cli.ids]))

            # Expand out id numbers if a range has been used:
            exp_ids = []
            for idn in self.ids:
                if '-' in idn:
                    range_start = int(idn.split('-')[0])
                    range_end = int(idn.split('-')[-1]) + 1
                    exp_range = [str(b) for b in range(range_start, range_end)]
                    exp_ids.extend(exp_range)
                else:
                    exp_ids.append(idn)
            self.ids = set(exp_ids)

        elif self.cli.use_date_range:
            # If using a date range instead of pipelines, get pipeline:
            msg = "Getting pipeline ids for between {0} and {1} (UTC)"
            self.cli.LOG.info(msg.format(self.cli.start.strftime(ts_format),
                                         self.cli.end.strftime(ts_format)))
            self.ids = buildtracker.get_pipelines_from_date_range(
                self.cli.start, self.cli.end)

        for pos, idn in enumerate(self.ids):
            if self.cli.use_deploy:
                try:
                    pipeline = buildtracker.get_pipeline_from_deploy_build(idn)
                except:
                    # Fall back to jenkins if test-catalog is down:
                    pipeline = ci_server.get_pipeline_from_deploy_build(idn)
            else:
                pipeline = idn
            # Quickly cycle through to check all pipelines are real:
            if not self.pipeline_check(pipeline):
                msg = "Pipeline ID \"%s\" is an unrecognised format" % pipeline
                self.cli.LOG.error(msg)
            else:
                self.pipeline_ids.append(pipeline)

            # Notify user of progress:
            checkin = 5 if len(self.pipeline_ids) > 20 else None
            pgr = self.calculate_progress(pos, self.ids, checkin)
            if pgr:
                self.cli.LOG.info("Pipeline lookup {0}% complete.".format(pgr))
        msg = "Pipeline lookup 100% complete: All pipelines checked. "
        msg += "Now downloading and processing data."
        self.cli.LOG.info(msg)
        return buildtracker.get_all_pipelines(self.pipeline_ids)

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
                pp_file.write("\n" + str(datetime.now()) +
                              "\n--------------------------\n")
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

    def enlist(self, thing):
        if type(thing) not in [list, tuple]:
            return [thing]
        elif type(thing) is tuple:
            return list(thing)
        else:
            return thing

    def find_indexes_of_occurrence(self, haystack, needle):
        """Find the start of all (possibly overlapping) instances of needle in
        haystack
        """
        offs = -1
        while True:
            offs = haystack.find(needle, offs + 1)
            if offs == -1:
                break
            else:
                yield offs

    def normalise_bug_details(self, pipelines, content):
        """Replace pipeline id with a placeholder pipeline id and then replace
        the strings specified in doberman_normalisation.json with an
        alternative, in the order given in that json file.
        """
        # replace pipeline id(s) with placeholder:
        pl_placeholder = 'AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'
        if content:
            for pipeline in self.enlist(pipelines):
                content = re.sub(pipeline, pl_placeholder, content)
        else:
            content = ''

        normalisers = self.cli.normalisers.get('normalisers')
        if normalisers is None:
            return content
        ordered_normalisers = OrderedDict(sorted(normalisers.items(),
                                          key=lambda t: t[1].get('order')))

        nrmlsd_content = content
        for name, normaliser in ordered_normalisers.items():
            nrmlsd_content = re.sub(normaliser['replace'], normaliser['with'],
                                    nrmlsd_content) if content else ''

        return nrmlsd_content

    def yield_error_signatures(self, full_text, file_to_scan, announce=True):
        """A generator method that extracts and yields isolated sections of
        content by matching sections of the given text to the error patterns
        provided by the doberman_patterns.json (i.e. it looks for 'Traceback',
        etc).
        """
        for pattern_type, details in self.cli.patterns['patterns'].items():

            # json.load makes this unicode, but this can lead to
            # UnicodeDecodeErrors, so convert to str object:
            details['start of pattern'] = str(details['start of pattern'])

            if not details["case sensitive"]:
                original_start_pattern = details['start of pattern']
                details['start of pattern'] = original_start_pattern.lower()
                full_text = full_text.lower()

            if details['start of pattern'] not in full_text:
                continue

            indexes = (self.find_indexes_of_occurrence(full_text,
                       details['start of pattern']))
            minlen = details["minimum pattern length"]

            prev_index = 0

            for index in indexes:
                start_idx = index
                error_text_prefix = ""
                error_text_suffix = ""
                error_text = None
                if details["preceding lines"] > 0:
                    # include n lines before start of pattern:
                    error_text_prefix = \
                        "".join(full_text[prev_index:start_idx].split('\n')
                                [-details["preceding lines"]:])
                elif not details["start inclusive"]:
                    # if you don't want the pattern itself (only what follows):
                    start_pattern_length = len(details["start of pattern"])
                    start_idx = start_idx + start_pattern_length

                # If end_idx is -1 then it means it will scan to the end of the
                # file. To avoid this, multiple end patterns can be provided,
                # and it will choose the one that results in the smallest text:
                if type(details['end of pattern']) != list:
                    end_patterns = [details['end of pattern']]
                else:
                    end_patterns = details['end of pattern']
                for position, end_pattern_unicode in enumerate(end_patterns):
                    end_pattern = str(end_pattern_unicode)
                    if not end_pattern:
                        end_idx = -1  # EOF
                    else:
                        st_ptrn = len(details["start of pattern"])
                        end_idx = full_text[index + st_ptrn:].find(end_pattern)
                        if end_idx != -1:
                            end_idx = end_idx + index + st_ptrn
                    if end_idx > 0 and details["following lines"] > 0:
                        # include n lines after end of pattern:
                        error_text_suffix = \
                            "".join(full_text[end_idx:].split('\n')
                                             [:details["following lines"]])
                    elif end_idx > 0 and details["end inclusive"]:
                        # if do want the end marker included in the pattern:
                        end_pattern_length = len(end_pattern) + 1
                        end_idx = end_idx + end_pattern_length

                    proposed_error_text = (error_text_prefix + full_text
                                           [index:end_idx] + error_text_suffix)

                    # Make sure that the the number of letters is greater than
                    # the minimum pattern length:
                    if minlen not in [None, ""]:
                        if len([ch for ch in proposed_error_text.lower() if ch
                                in 'abcdefghijklmnopqrstuvwxyz']) < minlen:
                            continue

                    if error_text is None:
                        error_text = proposed_error_text
                    else:
                        alt_error_text = proposed_error_text
                        alt_shorter = len(alt_error_text) < len(error_text)
                        if end_idx != -1 and alt_shorter:
                            error_text = alt_error_text
                if error_text is None:
                    continue

                prev_index = index
                yield (pattern_type, error_text)

    def pipeline_check(self, pipeline_id):
        try:
            return [8, 4, 4, 4, 12] == [len(x) for x in pipeline_id.split('-')]
        except:
            return False

    def remove_dirs(self, folders_to_remove):
        """Remove data folders used to store untarred artifacts (just leaving
        yaml files).
        """

        if type(folders_to_remove) not in [list, tuple, dict]:
            folders_to_remove = [folders_to_remove]

        if not self.cli.keep_data:
            for folder in folders_to_remove:
                kill_me = os.path.join(self.cli.reportdir, folder)
                if os.path.isdir(kill_me):
                    shutil.rmtree(kill_me)

    def report_time_taken(self, start_time, finish_time):
        """Report length of time Doberman took to complete"""
        time_taken = finish_time - start_time
        time_str = ':'.join(str(time_taken).split(':')[:3])
        return "Time to complete: {}".format(time_str)

    def convert_timestamp_to_dt_obj(self, timestamp):
        timestamp_in_ms = timestamp / 1000
        return datetime.fromtimestamp(timestamp_in_ms)

    def convert_timestamp_to_string(self, timestamp,
                                    ts_format='%a %d %b %Y %H:%M:%S'):
        dt_obj = self.convert_timestamp_to_dt_obj(timestamp)
        return dt_obj.strftime(ts_format)

    def load_bugs_from_yaml_file(self, db_yaml):
        with open(db_yaml, "r") as mock_db_file:
            return yaml.load(mock_db_file).get('bugs')
