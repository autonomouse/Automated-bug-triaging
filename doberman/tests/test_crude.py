import os
import yaml
import tempfile
import shutil
from doberman.tests.test_utils import DobermanTestBase
from doberman.analysis.analysis import CrudeAnalysis
from doberman.common import utils
from doberman.__init__ import __version__
from collections import namedtuple
from lxml import etree
from random import randrange


class CrudeAnalysisTests(DobermanTestBase):

    mock_data_dir = "./doberman/mock_data/"
    mock_output_data = os.path.abspath(os.path.join(mock_data_dir, "output"))
    DB_files = os.path.abspath(os.path.join(mock_data_dir, "database_files"))
    real_db_yaml = "../../../samples/mock_database.yml"
    pipeline_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    paabn_info = {'pipeline_deploy': '00001',
                  'pipeline_prepare': '00002',
                  'pipeline_start': '00000',
                  'test_tempest_smoke': '00003'}

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
            path_to_file = os.path.join(self.mock_data_dir, filename)
            if os.path.exists(path_to_file):
                os.remove(path_to_file)
        if hasattr(self, 'tmpdir'):
            shutil.rmtree(self.tmpdir)

    def get_output_data(self, fname="triage_pipeline_deploy.yml",
                        output_data_dir=mock_output_data):
        with open(os.path.join(output_data_dir, fname),'r') as f:
            output = yaml.load(f)
        return output['pipeline'][self.pipeline_id]

    def populate_cli_var(self, bugs_database, reportdir=mock_output_data):
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
        cli.reportdir = reportdir
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

    def create_paabn_in_tmp_dir(self):
        tmpdir = tempfile.mkdtemp()
        tmpfile = os.path.join(tmpdir,
                               "pipelines_and_associated_build_numbers.yml")
        paabn = {"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee": self.paabn_info}
        with open(tmpfile, 'a+') as f:
            f.write(yaml.safe_dump(paabn, default_flow_style=False))
        return tmpdir

    def create_mock_xml_files(self, add_to_xml_dict):
        for xml_file in add_to_xml_dict:
            root = etree.Element("root")
            testsuite = etree.SubElement(root, "testsuite")
            for line in add_to_xml_dict[xml_file]:
                testcase = etree.SubElement(testsuite, "testcase")
                testcase.text = line
                random = randrange(0,99)
                testcase.attrib['classname'] = "fake_class_{}".format(random)
                testcase.attrib['name'] = "fake_testname_{}".format(random)
        etree.ElementTree(root).write(xml_file, pretty_print=True)

    # Tests:
    def test_build_number_in_output(self):
        cli = self.populate_cli_var("blank_database.yml")
        analysis = CrudeAnalysis(cli)
        data = self.get_output_data()
        self.assertEqual(data['build'], '00000')

    def test_find_console_bug(self):
        cli = self.populate_cli_var("fake_bug_01_database.yml")
        analysis = CrudeAnalysis(cli)
        data = self.get_output_data()
        self.assertIn("fake_bug_01", data['bugs'])

    def test_find_unfiled_console_bug(self):
        cli = self.populate_cli_var("blank_database.yml")
        analysis = CrudeAnalysis(cli)
        data = self.get_output_data()
        self.assertNotIn("fake_bug_01", data['bugs'])
        self.assertIn("unfiled-", data['bugs'].keys()[0])

    def test_bug_loaded_into_in_bugs_dictionary(self):
        cli = self.populate_cli_var("glob_matched_filename_bug_database.yml")
        analysis = CrudeAnalysis(cli)
        self.assertIn('fake_bug_02', analysis.test_catalog.bugs)

    def test_returns_zero_unless_error(self):
        cli = self.populate_cli_var("glob_matched_filename_bug_database.yml")
        analysis = CrudeAnalysis(cli)
        self.assertEqual(0, analysis.message)

