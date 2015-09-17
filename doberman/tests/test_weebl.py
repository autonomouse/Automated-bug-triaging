import os
import yaml
import pytz
from common_test_methods import CommonTestMethods
from doberman.analysis.analysis import CrudeAnalysis
from doberman.common.options_parser import OptionsParser
from datetime import datetime
from mock import (
    Mock,
    patch,
    )


class CrudeAnalysisTests(CommonTestMethods):
    def setUp(self):
        super(CrudeAnalysisTests, self).setUp()
        self.reportdir = self.mock_output_data
        self.tidy_up()

    def tearDown(self):
        super(CrudeAnalysisTests, self).tearDown()
        self.tidy_up()

    @patch('weeblclient.weebl_python2.weebl.Weebl.weeblify_environment')
    @patch('weeblclient.weebl_python2.weebl.Weebl.create_pipeline')
    @patch('weeblclient.weebl_python2.weebl.Weebl.create_build')
    @patch('weeblclient.weebl_python2.weebl.Weebl.create_bug_occurrence')
    @patch('weeblclient.weebl_python2.weebl.Weebl.get_bug_info')
    def test_use_weebl(self, _get_bug_info, _create_bug_occurrence, _create_build, 
                       _create_pipeline, _weeblify_environment):
        cli = self.populate_cli_var("blank_database.yml")
        cli.use_weebl = True
        analysis = CrudeAnalysis(cli)
        _weeblify_environment.assert_called_with(
            analysis.cli.jenkins_host, analysis.jenkins)
        _create_pipeline.assert_called_with(
                'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
                'ci-oil-slave4-1')
