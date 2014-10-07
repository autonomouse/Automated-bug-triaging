
import yaml
from test_catalog.client.api import TCClient
from test_catalog.client.base import TCCTestPipeline
from doberman.common import pycookiecheat, utils
from jenkinsapi.custom_exceptions import *

LOG = utils.get_logger('doberman.analysis')

class Common(object):
    """ Common methods  
    """

    def add_to_yaml(self, matching_bugs, build_status, link, existing_dict):
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

            if link:
                pipeline_dict[self.pipeline]['link to jenkins'] = \
                    self.cli.jenkins_host + link
            pipeline_dict[self.pipeline]['link to test-catalog'] = \
                self.cli.tc_host.replace('api', "pipeline/" + self.pipeline)

        # Merge with existing dict:
        if existing_dict:
            if 'pipeline' in existing_dict:
                yaml_dict['pipeline'] = self.join_dicts(existing_dict['pipeline'],
                                                   pipeline_dict)
            else:
                yaml_dict['pipeline'] = self.join_dicts(existing_dict, pipeline_dict)
        else:
            yaml_dict['pipeline'] = pipeline_dict
        return yaml_dict

    def non_db_bug(self, bug_id, existing_dict, err_msg):
        """ Make non-database bugs for special cases, such as missing files that
            cannot be, or are not yet, listed in the bugs database.

        """
        matching_bugs = {}
        matching_bugs[bug_id] = {'regexps': err_msg, 'vendors': err_msg,
                                 'machines': err_msg, 'units': err_msg}
        yaml_dict = self.add_to_yaml(matching_bugs, 'FAILURE', None, existing_dict)
        return yaml_dict

    def join_dicts(self, old_dict, new_dict):
        """ Merge matching_bugs dictionaries. """
        earlier_items = list(old_dict.items())
        current_items = list(new_dict.items())
        return dict(earlier_items + current_items)


