import os
import yaml
import pytz
import doberman
import common_test_methods
from test_crude import CrudeAnalysisTests
from doberman.analysis.analysis import CrudeAnalysis
from doberman.common.options_parser import OptionsParser
from datetime import datetime
from mock import patch, MagicMock, Mock
from common_test_methods import CommonTestMethods
from weebl_python2.weebl import Weebl

reportdir = common_test_methods.mock_output_data

def mock_tc_init(self, cli):
    self.bugs = MagicMock()


def mock_jkns_init(self, cli):
    self.jenkins_api = MagicMock()


class WeeblTests(CommonTestMethods):
    """Repeat the CrudeAnalysisTests with use_weebl set as True."""
   
    def populate_cli_var(self, bugs_database, reportdir=reportdir):
        cli = super(WeeblTests, self).populate_cli_var(
            bugs_database, reportdir)
        cli.use_weebl = True
        cli.weebl_ip = "http://127.0.0.1:8000" # need to mock this
        cli.weebl_auth = ("weebl", "passweebl")
        cli.weebl_api_ver = 'v1'        
    
    def get_bugs_from_file(self, bugs_database):
        database = os.path.join(self.DB_files, bugs_database)
        with open(database, "r") as mock_db_file:
            return yaml.load(mock_db_file)['bugs']

    @patch.object(Weebl, 'weeblify_environment')
    @patch.object(Weebl, 'create_pipeline')
    @patch.object(doberman.analysis.crude_test_catalog.TestCatalog, 
                  'get_all_pipelines')
    def test_pipeline_integration(self, weeblify_environment, create_pipeline,
                                  get_all_pipelines):
        with patch('doberman.analysis.crude_test_catalog.TestCatalog.__init__', 
                   mock_tc_init):
            mock_tc_init.return_value = None
            mock_tc_init.bugs = self.get_bugs_from_file("blank_database.yml")
            with patch('doberman.analysis.crude_jenkins.Jenkins', 
                       mock_jkns_init):    
                mock_jkns_init.return_value = None      
                get_all_pipelines.return_value = self.paabn_info
