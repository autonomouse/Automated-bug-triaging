
import os
import yaml
from test_catalog.client.api import TCClient
from test_catalog.client.base import TCCTestPipeline
from doberman.common import pycookiecheat
from doberman.common.base import DobermanBase
from jenkinsapi.custom_exceptions import *


class TestCatalog(DobermanBase):

    def __init__(self, cli):
        self.cli = cli
        self.verify = self.cli.verify
        self.tc_client = TCClient
        self._tc_client = []
        self.bugs = None
        if not self.cli.offline_mode:
            self.cookie = self.cli.tc_auth
            self.get_tc_client()
        self.open_bug_database()  # Connect to bugs DB

    def open_bug_database(self):
        if self.cli.database in [None, 'None', 'none', '']:
            if not self.cli.offline_mode:
                self.cli.LOG.info("Connecting to test-catalog bug database")
                self.bugs = \
                    self.client.get_bug_info(force_refresh=False)['bugs']
            else:
                emsg = "In offline mode, but no local database file provided!!"
                self.cli.LOG.error(emsg)
                raise Exception(emsg)
        elif len(self.cli.database):
            self.cli.LOG.info("Connecting to database file: %s"
                              % (self.cli.database))
            with open(self.cli.database, "r") as mock_db_file:
                self.bugs = yaml.load(mock_db_file)['bugs']
        else:
            self.cli.LOG.error('Unknown database: %s' % (self.cli.database))
            raise Exception('Invalid Database configuration')

    def get_tc_client(self):
        if self._tc_client and not self.cli.tc_host:
            self.client = self._tc_client[0]
        self.connect_to_testcatalog()
        self._tc_client.append(self.client)

    def connect_to_testcatalog(self):
        self.cli.LOG.debug('Connecting to test-catalog @ %s remote=%s'
                           % (self.cli.tc_host, self.cli.run_remote))
        if self.cookie is None:
            self.cli.LOG.info("Fetching test-catalog cookies for %s"
                              % self.cli.tc_host)
            self.cookie = pycookiecheat.chrome_cookies(self.cli.tc_host)
        self.cli.LOG.info("Fetching test-catalog using endpoint=%s"
                          % self.cli.tc_host)
        self.client = self.tc_client(endpoint=self.cli.tc_host,
                                     cookies=self.cookie, verify=self.verify)

    def get_pipelines_from_paabn(self, filename=None):
        if not filename:
            filename = 'pipelines_and_associated_build_numbers.yml'
        if filename in os.listdir(self.cli.reportdir):
            with open(os.path.join(self.cli.reportdir, filename), "r") as f:
                return yaml.load(f)
        return {}

    def get_all_pipelines(self, pipeline_ids):
        build_numbers = {}
        self.mkdir(self.cli.reportdir)

        # The local dictionary way:
        filename = 'pipelines_and_associated_build_numbers.yml'
        build_numbers = self.get_pipelines_from_paabn(filename)

        # Check that all pipeline_ids were in the yaml file:
        if build_numbers:
            missing = [pl for pl in pipeline_ids if pl not in
                       build_numbers.keys()]
        else:
            missing = pipeline_ids

        if missing:
            # The test catalog way:
            for pipeline_id in missing:
                pldata = self.get_pipelines(pipeline_id)
                if pldata:
                    build_numbers[pipeline_id] = pldata

            # Create local dictionary for next time:
            self.write_output_yaml(self.cli.reportdir, filename, build_numbers)

        # Remove any pipelines that shouldn't be there (keep in the paabn
        # though - no need to lose good data):
        for pipeline in build_numbers.keys():
            if pipeline not in pipeline_ids:
                build_numbers.pop(pipeline)

        self.cli.LOG.info("Returning {} pipelines".format(len(build_numbers)))
        return build_numbers

    def get_pipelines(self, pipeline):
        """ Using test-catalog, return the build numbers for the jobs that are
            part of the given pipeline.
        """
        try:
            pl_tcat = TCCTestPipeline(self.client, pipeline)
        except Exception as e:
            msg = "test-catalog error. Does pipeline exist? Is there a cookie-"
            msg += "related issue? (%s)" % e
            self.cli.LOG.error(msg)
            return

        build_numbers = {}
        parent_dict = str(pl_tcat.__dict__)

        for jname in self.cli.job_names:
            try:
                text = parent_dict.split(jname)[1].split(',')[0]
                build = text.replace('/', '').replace('-', '').replace("'", '')
                build_numbers[jname] = build
            except:
                build_numbers[jname] = None
        bstr = ", ".join(["{} ({})".format(val, key)
                          for key, val in build_numbers.items() if val])
        msg = 'Build numbers {1} associated with pipeline: {0}'
        self.cli.LOG.debug(msg.format(pipeline, bstr))
        return build_numbers

    def get_pipelines_from_date_range(self, start, end, limit=2000):
        start_date = 'start="{}"'.format(start.strftime('%c'))
        end_date = 'end="{}"'.format(end.strftime('%c'))
        params = [start_date, end_date]
        return self.client.search_pipelines(params, limit=limit, extra=False)

    def get_pipeline_from_deploy_build(self, id_number,
                                       job='jenkins-pipeline_deploy'):
        data = self.client.get_job_by_build_tag('{}-{}'.format(job, id_number))
        return data.get('pipeline_id')
