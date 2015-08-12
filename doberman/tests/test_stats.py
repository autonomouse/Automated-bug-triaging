import os
import yaml
import pytz
from common_test_methods import CommonTestMethods
from doberman.analysis.analysis import CrudeAnalysis
from doberman.common.options_parser import OptionsParser
from datetime import datetime


class StatsTests(CommonTestMethods):
    def setUp(self):
        super(StatsTests, self).setUp()
        self.reportdir = self.mock_output_data
        self.tidy_up()

    def tearDown(self):
        super(StatsTests, self).tearDown()
        self.tidy_up()

    # def test_success_rate_not_gt_100(self):
    #     import pdb; pdb.set_trace()
