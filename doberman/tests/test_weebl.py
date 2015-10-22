import os
import yaml
import pytz
import weeblclient
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
    @patch('weeblclient.weebl_python2.weebl.Weebl.get_bug_info')
    @patch('weeblclient.weebl_python2.weebl.Weebl.buildexecutor_exists')
    @patch('weeblclient.weebl_python2.weebl.Weebl.create_buildexecutor')
    @patch('weeblclient.weebl_python2.weebl.Weebl.pipeline_exists')
    @patch('weeblclient.weebl_python2.weebl.Weebl.create_pipeline')
    @patch('weeblclient.weebl_python2.weebl.Weebl.build_exists')
    @patch('weeblclient.weebl_python2.weebl.Weebl.create_build')
    @patch('weeblclient.weebl_python2.weebl.Weebl.update_build')
    @patch('weeblclient.weebl_python2.weebl.Weebl.bugoccurrence_exists')
    @patch('weeblclient.weebl_python2.weebl.Weebl.create_bugoccurrence')
    def test_use_weebl(self, _create_bugoccurrence, _bugoccurrence_exists,
                       _update_build, _create_build, _build_exists,
                       _create_pipeline, _pipeline_exists,
                       _create_buildexecutor, _buildexecutor_exists,
                       _get_bug_info, _weeblify_environment):
        cli = self.populate_cli_var("blank_database.yml")
        cli.use_weebl = True
        analysis = CrudeAnalysis(cli)
        _weeblify_environment.assert_called_with(
            analysis.cli.jenkins_host, analysis.jenkins)
        _create_pipeline.assert_called_with(
                'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
                'ci-oil-slave4-1')
