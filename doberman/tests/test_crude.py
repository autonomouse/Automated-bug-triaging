import os
import yaml
from doberman.tests.test_utils import DobermanTestBase
from doberman.analysis.analysis import CrudeAnalysis
from doberman.common import utils
from doberman.__init__ import __version__
from collections import namedtuple

class CrudeAnalysisTests(DobermanTestBase):

    mock_data_dir = "./doberman/mock_data/"
    mock_output_data = os.path.abspath(os.path.join(mock_data_dir, "output"))
    DB_files = os.path.abspath(os.path.join(mock_data_dir, "database_files"))

    # Support Methods:
    def setUp(self):
        super(CrudeAnalysisTests, self).setUp()
        self.tidy_up()

    def tearDown(self):
        super(CrudeAnalysisTests, self).tearDown()
        self.tidy_up()

    def tidy_up(self):
        files_to_ditch = ["pipelines_processed.yaml",
                          "triage_pipeline_deploy.yml",
                          "triage_pipeline_prepare.yml",
                          "triage_test_tempest_smoke.yml"]
        for filename in files_to_ditch:
            try:
                os.remove(os.path.join(self.data_dir, filename))
            except:
                pass

    def get_deploy_output_data(self):
        pipeline_id = 'ec832ce3-4393-4d4f-ab06-06836ea47e08'
        fname = "triage_pipeline_deploy.yml"
        with open(os.path.join(self.mock_output_data, fname),'r') as f:
            output = yaml.load(f)
        return output['pipeline'][pipeline_id]

    def populate_cli_var(self, bugs_database="blank_database.yml"):
        cli = namedtuple('CLI', '')
        cli.crude_job = 'pipeline_start'
        cli.database = os.path.join(self.DB_files, bugs_database)
        cli.dont_replace = True
        cli.external_jenkins_url = 'http://oil-jenkins.canonical.com'
        cli.ids = set(['doberman/tests/test_crude.py'])
        cli.jenkins_host = 'http://oil-jenkins.canonical.com'
        cli.job_names = ['pipeline_start', 'pipeline_deploy',
                              'pipeline_prepare', 'test_tempest_smoke']
        cli.keep_data = False
        cli.logpipelines = False
        cli.match_threshold = '0.965'
        cli.netloc = '91.189.92.95'
        cli.offline_mode = True
        cli.reduced_output_text = False
        cli.reportdir = self.mock_output_data
        cli.run_remote = True
        cli.tc_host = 'https://oil.canonical.com/api'
        cli.use_date_range = False
        cli.use_deploy = False
        cli.verify = True
        cli.xmls = ['tempest_xunit.xml']

        LOG = utils.get_logger('doberman.analysis')
        LOG.info("Doberman version {0}".format(__version__))
        cli.LOG = LOG
        return cli

    # Tests:
    def test_build_number_in_output(self):
        cli = self.populate_cli_var()
        analysis = CrudeAnalysis(cli)
        data = self.get_deploy_output_data()
        self.assertTrue(data.get('build') == '00000')

    def test_find_console_bug(self):
        cli = self.populate_cli_var("fake_bug_01_database.yml")
        analysis = CrudeAnalysis(cli)
        data = self.get_deploy_output_data()
        self.assertTrue('fake_bug_01' in data.get('bugs'))

    def test_find_unfiled_console_bug(self):
        cli = self.populate_cli_var()
        analysis = CrudeAnalysis(cli)
        data = self.get_deploy_output_data()
        self.assertTrue("fake_bug_01" not in data.get('bugs'))
        self.assertTrue("unfiled-" in data.get('bugs').keys()[0])

    def test_bug_loaded_into_in_bugs_dictionary(self):
        cli = self.populate_cli_var("glob_matched_filename_bug_database.yml")
        analysis = CrudeAnalysis(cli)
        self.assertTrue('fake_bug_02' in analysis.test_catalog.bugs)

    def test_correct_error_message(self):
        """
        This is a test to make sure zeros are returned unless there is an error
        """
        cli = self.populate_cli_var("glob_matched_filename_bug_database.yml")
        analysis = CrudeAnalysis(cli)
        self.assertTrue(analysis.message is 0)


