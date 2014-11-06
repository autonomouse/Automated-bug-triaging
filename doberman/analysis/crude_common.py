import os
import yaml
import datetime
import special_cases
from jenkinsapi.custom_exceptions import *


class Common(object):
    """ Common methods
    """

    def add_to_yaml(self, matching_bugs, build_status, existing_dict):
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
                datetime.datetime.utcnow().strftime('%Y-%B-%d %H:%M:%S.%f')
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

    def non_db_bug(self, bug_id, existing_dict, err_msg):
        """ Make non-database bugs for special cases, such as missing files
            that cannot be, or are not yet, listed in the bugs database.

        """
        jlink = '{0}/job/{1}/{2}/console'.format(self.cli.external_jenkins_url,
                                                 self.jobname,
                                                 self.build_number)
        matching_bugs = {}
        matching_bugs[bug_id] = {'regexps': err_msg, 'vendors': err_msg,
                                 'machines': err_msg, 'units': err_msg,
                                 'link to jenkins': jlink}
        try:
            self.cli.LOG.info("Special case bug found! '{0}' ({1}, bug #{2})"
                              .format(err_msg, self.jobname, bug_id))
            yaml_dict = self.add_to_yaml(matching_bugs, 'FAILURE',
                                         existing_dict)
        except:
            self.cli.LOG.info("Special case bug found! '{0}' (bug #{1})"
                              .format(err_msg, bug_id))
            yaml_dict = self.add_to_yaml(matching_bugs, 'FAILURE', None,
                                         existing_dict)
        self.message = 0
        return yaml_dict

    def join_dicts(self, old_dict, new_dict):
        """ Merge matching_bugs dictionaries. """
        earlier_items = list(old_dict.items())
        current_items = list(new_dict.items())
        return dict(earlier_items + current_items)

    def write_output_yaml(self, output_dir, filename, yaml_dict):
        """
        """
        file_path = os.path.join(output_dir, filename)
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)
        with open(file_path, 'w') as outfile:
            outfile.write(yaml.safe_dump(yaml_dict, default_flow_style=False))
            self.cli.LOG.info(filename + " written to "
                              + os.path.abspath(output_dir))

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
        except IOError, e:
            fname = file_location.split('/')[-1]
            self.cli.LOG.error("%s: %s is not in artifacts folder (%s)"
                               % (self.pipeline, fname, e[1]))
            msg = fname + ' MISSING'
            yaml_dict = self.non_db_bug(special_cases.bug_dict[fname],
                                        yaml_dict, msg)
            return (None, yaml_dict)

    def dictator(self, dictionary, dkey, dvalue):
        """ Adds dvalue to list in a given dictionary (self.oil_df/oil_nodes).
            Assumes that dictionary will be self.oil_df, self.oil_nodes, etc so
            nothing is returned.

        """

        if dkey not in dictionary:
            dictionary[dkey] = []
        dictionary[dkey].append(dvalue)
