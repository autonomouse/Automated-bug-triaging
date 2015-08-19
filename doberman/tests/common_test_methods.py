import os
import yaml
import json
import tempfile
import shutil
from doberman.tests.test_utils import DobermanTestBase
from doberman.tests.regex import generate_from_regex
from doberman.common import utils
from doberman.__init__ import __version__
from collections import namedtuple
from lxml import etree

mock_data_dir = "./doberman/tests/mock_data/"
mock_output_data = os.path.abspath(os.path.join(mock_data_dir, "output"))


class CommonTestMethods(DobermanTestBase):

    mock_data_dir = mock_data_dir
    mock_output_data = mock_output_data
    DB_files = os.path.abspath(os.path.join(mock_data_dir, "database_files"))
    real_db_yaml = "../../../../samples/mock_database.yml"
    pipeline_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    paabn_info = {'pipeline_deploy': '00001',
                  'pipeline_prepare': '00002',
                  'pipeline_start': '00000',
                  'test_tempest_smoke': '00003',
                  'test_cloud_image': '00004',
                  'test_bundletests': '00005'}

    def tidy_up(self):
        files_to_ditch = ["pipelines_processed.yaml",
                          "triage_pipeline_deploy.yml",
                          "triage_pipeline_prepare.yml",
                          "triage_test_tempest_smoke.yml",
                          "triage_test_cloud_image.yml",
                          "triage_test_bundletests.yml"]
        for filename in files_to_ditch:
            path_to_file = os.path.join(self.reportdir, filename)
            if os.path.exists(path_to_file):
                os.remove(path_to_file)
        if hasattr(self, 'tmpdir'):
            shutil.rmtree(self.tmpdir)

    def get_output_data(self, fname, output_data_dir):
        try:
            with open(os.path.join(output_data_dir, fname),'r') as f:
                return yaml.load(f)
        except IOError:
            return

    def get_crude_output_data(self, fname="triage_pipeline_deploy.yml",
                        output_data_dir=mock_output_data):
        try:
            data = self.get_output_data(fname, output_data_dir)
            return None if data is None else data['pipeline'][self.pipeline_id]
        except KeyError:
            return {'bugs': {}}

    def get_refinery_output_data(self, fname="bug_ranking_pipeline_deploy.yml",
                        output_data_dir=mock_output_data):
        try:
            return self.get_output_data(fname, output_data_dir)
        except KeyError:
            return

    def populate_cli_var(self, bugs_database, reportdir=mock_output_data): 
        cli = namedtuple('CLI', '')
        cli.crude_job = 'pipeline_start'
        cli.database = os.path.join(self.DB_files, bugs_database)
        cli.dont_replace = True
        cli.external_jenkins_url = 'http://oil-jenkins.canonical.com'
        cli.ids = set(['doberman/tests/test_crude.py'])
        cli.jenkins_host = 'http://oil-jenkins.canonical.com'
        cli.job_names = ['pipeline_start', 'pipeline_deploy',
                         'pipeline_prepare', 'test_tempest_smoke',
                         'test_cloud_image', 'test_bundletests']
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
        cli.dont_scan = ".pyc .tar .gz wtmp"
        cli.multi_bugs_in_pl = "test_tempest_smoke"
        self.max_sequence_size = '10000'
        cli.bug_tracker_bugs_url = "https://bugs.launchpad.net/oil/+bug/{}"
        cli.generic_bug_id = "GenericBug_Ignore"
        cli.bug_tracker_url = "https://bugs.launchpad.net/bugs/{}"
        cli.environment = "TestEnvironment"

        # WEEBL:
        cli.use_weebl = False
        #
        
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
        dashes = "--------------------"
        larrow = "<<" + dashes
        rarrow = dashes + ">>"
        msg = " begin captured logging "
        for xml_file in add_to_xml_dict:
            root = etree.Element("root")
            testsuite = etree.SubElement(root, "testsuite")
            for (bug_number, line) in add_to_xml_dict[xml_file]:
                testcase = etree.SubElement(testsuite, "testcase")
                testcase.attrib['classname'] = "fake_class_{}".format(bug_number)
                testcase.attrib['name'] = "fake_testname_{}".format(bug_number)
                failure = etree.SubElement(testcase, "failure")
                failure.attrib['type'] = "fake_type_{}".format(bug_number)
                failure.attrib['message'] =\
                    "{}{}{}\n{}\n{}".format(rarrow, msg, larrow, line, dashes)
        etree.ElementTree(root).write(xml_file, pretty_print=True)

    def generate_text_from_regexp(self, regexp):
        return generate_from_regex(regexp)
