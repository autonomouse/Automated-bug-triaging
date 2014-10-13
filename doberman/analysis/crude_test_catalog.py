
from crude_common import Common

import yaml
from test_catalog.client.api import TCClient
from test_catalog.client.base import TCCTestPipeline
from doberman.common import pycookiecheat
from jenkinsapi.custom_exceptions import *


class TestCatalog(Common):
    """
    """

    def __init__(self, cli):
        self.cli = cli
        self.cookie = self.cli.tc_auth
        self.tc_client = TCClient
        self._tc_client = []
        self.bugs = None
        self.get_tc_client()
        self.open_bug_database()  # Connect to bugs DB

    def open_bug_database(self):
        if self.cli.database in [None, 'None', 'none', '']:
            self.cli.LOG.info("Connecting to test-catalog bug/regex database")
            self.b = self.client.get_bug_info(force_refresh=True)
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
                                     cookies=self.cookie)

    def get_pipelines(self, pipeline):
        """ Using test-catalog, return the build numbers for the jobs that are
            part of the given pipeline.

        """
        self.cli.LOG.info('Fetching data on pipeline: %s' % (pipeline))
        try:
            pl_tcat = TCCTestPipeline(self.client, pipeline)
        except Exception, e:
            msg = "test-catalog error. Does pipeline exist? Is there a cookie-"
            msg += "related issue? (%s)" % e
            self.cli.LOG.error(msg)
            raise Exception(msg)

        build_numbers = {}
        parent_dict = str(pl_tcat.dict['parent'])

        for jname in self.cli.job_names:
            try:
                text = parent_dict.split(jname)[1].split(',')[0]
                build = text.replace('/', '').replace('-', '').replace("'", '')
                build_numbers[jname] = build
            except:
                build_numbers[jname] = None
        return build_numbers

    def pipeline_check(self, pipeline_id):
        return [8, 4, 4, 4, 12] == [len(x) for x in pipeline_id.split('-')]
