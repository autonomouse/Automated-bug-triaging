import os
from common_test_methods import CommonTestMethods
from doberman.refinery.refinery import Refinery


class RefineryTests(CommonTestMethods):
    def setUp(self):
        super(RefineryTests, self).setUp()
        self.reportdir = self.mock_output_data
        self.tidy_up()

    def tearDown(self):
        super(RefineryTests, self).tearDown()
        self.tidy_up()

    def test_display_top_ten_bugs_returns_zero_when_no_generics(self):
        job_names = ['pipeline_deploy']
        bug_rankings = {'all_bugs': [('bug1', 1), ('bug2', 2)],
                        'pipeline_deploy': [('bug1', 1), ('bug2', 2)]}
        cli = self.populate_cli_var("blank_database.yml")
        refinery = Refinery(cli, dont_print=True)
        output, top_ten = refinery.format_top_ten_bugs(
            job_names, bug_rankings)
        
        self.assertEqual(output, {'pipeline_deploy': 0})

    def test_display_top_ten_bugs_returns_correct_number_of_generics(self):
        gen_bug = 'bug2'
        num_gnrcs = '77'
        job_names = ['pipeline_deploy']
        bug_rankings = {'all_bugs': [('bug1', 1), ('bug2', 2)],
                        'pipeline_deploy': [('bug1', 1), (gen_bug, num_gnrcs)]}
        cli = self.populate_cli_var("blank_database.yml")
        cli.generic_bug_id = gen_bug
        refinery = Refinery(cli, dont_print=True)
        output, top_ten = refinery.format_top_ten_bugs(
            job_names, bug_rankings)
        self.assertEqual(output, {'pipeline_deploy': num_gnrcs})
