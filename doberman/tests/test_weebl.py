import os
import yaml
import pytz
from common_test_methods import CommonTestMethods
from doberman.analysis.analysis import CrudeAnalysis, Jenkins
from doberman.common.options_parser import OptionsParser
from datetime import datetime
from mock import (
    Mock,
    patch,
    )
from mock import patch, MagicMock


class CrudeAnalysisTests(CommonTestMethods):
    def setUp(self):
        super(CrudeAnalysisTests, self).setUp()
        self.reportdir = self.mock_output_data
        self.tidy_up()

    def tearDown(self):
        super(CrudeAnalysisTests, self).tearDown()
        self.tidy_up()

    @patch('weeblclient.weeblclient.tastypie_client.ApiClient.'
           + '_populate_resources')
    @patch('weeblclient.weeblclient.oldweebl.OldWeebl.weeblify_environment')
    @patch('weeblclient.weeblclient.weebl.Weebl.get_bug_info')
    @patch('weeblclient.weeblclient.oldweebl.OldWeebl.buildexecutor_exists')
    @patch('weeblclient.weeblclient.oldweebl.OldWeebl.create_buildexecutor')
    @patch('weeblclient.weeblclient.oldweebl.OldWeebl.pipeline_exists')
    @patch('weeblclient.weeblclient.weebl.Weebl.create_pipeline')
    @patch('weeblclient.weeblclient.oldweebl.OldWeebl.build_exists')
    @patch('weeblclient.weeblclient.oldweebl.OldWeebl.create_build')
    @patch('weeblclient.weeblclient.oldweebl.OldWeebl.update_build')
    @patch('weeblclient.weeblclient.oldweebl.OldWeebl.bugoccurrence_exists')
    @patch('weeblclient.weeblclient.oldweebl.OldWeebl.create_bugoccurrence')
    @patch('weeblclient.weeblclient.oldweebl.OldWeebl.'
           + 'get_build_uuid_from_build_id_job_and_pipeline')
    def test_use_weebl(self, _get_build_uuid_from_build_id_job_and_pipeline,
                       _create_bugoccurrence, _bugoccurrence_exists,
                       _update_build, _create_build, _build_exists,
                       _create_pipeline, _pipeline_exists,
                       _create_buildexecutor, _buildexecutor_exists,
                       _get_bug_info, _weeblify_environment,
                       _populate_resources):
        cli = self.populate_cli_var("blank_database.yml")
        cli.use_weebl = True
        analysis = CrudeAnalysis(cli)
        _weeblify_environment.assert_called_with(
            analysis.cli.jenkins_host, analysis.jenkins)
