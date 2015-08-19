import os
import yaml
import pytz
from test_crude import CrudeAnalysisTests
from doberman.analysis.analysis import CrudeAnalysis
from doberman.common.options_parser import OptionsParser
from datetime import datetime
from mock import patch, MagicMock
import common_test_methods

reportdir = common_test_methods.mock_output_data


class WeeblTests(CrudeAnalysisTests):
    """Repeat the CrudeAnalysisTests with use_weebl set as True."""
    def populate_cli_var(self, bugs_database, reportdir=reportdir):
        cli = super(CrudeAnalysisTests, self).populate_cli_var(
            bugs_database, reportdir)
        cli.use_weebl = True
        cli.weebl_ip = "http://127.0.0.1:8000" # need to mock this
        cli.weebl_auth = ("weebl", "passweebl")
        cli.weebl_api_ver = 'v1'
        
        # I'm going to need to mock self.jenkins.jenkins_api as well as weebl
