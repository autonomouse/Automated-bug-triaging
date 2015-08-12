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

    def test_stats(self):
        import pdb; pdb.set_trace()
        
'''
TESTS
-----

Overall Success Rate not > 100.00
'''



'''        
        cli = self.populate_cli_var("blank_database.yml")
        analysis = CrudeAnalysis(cli)
        data = self.get_crude_output_data()
        self.assertEqual(data['build'], '00000')

    def test_find_console_bug(self):
        cli = self.populate_cli_var("fake_bug_01_database.yml")
        analysis = CrudeAnalysis(cli)
        data = self.get_crude_output_data()
        self.assertIn("fake_bug_01", data['bugs'])

    def test_find_unfiled_console_bug(self):
        cli = self.populate_cli_var("blank_database.yml")
        analysis = CrudeAnalysis(cli)
        data = self.get_crude_output_data()
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

    def test_create_bugs_from_latest_mock_database_and_find_them(self):

        self.tmpdir = self.create_paabn_in_tmp_dir()
        cli = self.populate_cli_var(self.real_db_yaml,
                                    reportdir=self.tmpdir)
        cli.job_names = ['pipeline_start', 'pipeline_deploy',
                         'pipeline_prepare', 'test_tempest_smoke']

        real_DB = os.path.abspath(os.path.join(self.mock_output_data,
                                               self.real_db_yaml))

        jobs = []
        with open(real_DB, 'r') as bugs_db:
            bugs = yaml.load(bugs_db).get('bugs')

        add_to_xml_dict = {}
        for bug in bugs.items():
            bug_number = bug[0]
            bug_keys = bug[1].keys()
            bug_keys.remove('category')
            bug_keys.remove('description')
            for job in bug_keys:
                if job not in jobs:
                    jobs.append(job)
                job_dir = os.path.join(self.tmpdir, job,
                                       self.paabn_info[job])
                if not os.path.exists(job_dir):
                    os.makedirs(job_dir)
                for bug_details in bug[1][job]:
                    filename = bug_details.keys()[0]
                    regexp = bug_details[filename].get('regexp')
                    if type(regexp) == list:
                        regexp = regexp[0]
                    text = self.generate_text_from_regexp(regexp)
                    expanded_filename = filename.replace('*', 'xxx')
                    if filename == "console.txt":
                        expanded_filename = "{}_console.txt".format(job)
                    tmpfile = os.path.join(job_dir, expanded_filename)
                    if expanded_filename in cli.xmls:
                        if tmpfile not in add_to_xml_dict:
                            add_to_xml_dict[tmpfile] = []
                        add_to_xml_dict[tmpfile].append((bug_number, text))
                    else:
                        # yaml files need to be valid yaml;
                        # this makes it a list of strings.
                        if 'juju_status.yaml' in tmpfile:
                            text = "- '%s'" % (text)
                        with open(tmpfile, 'a+') as f:
                            f.write(text + "\n")
        if add_to_xml_dict:
            self.create_mock_xml_files(add_to_xml_dict)

        analysis = CrudeAnalysis(cli)

        bugs_found = []
        for job in jobs:
            fn = "triage_{}.yml".format(job)
            data = self.get_crude_output_data(fname=fn,
                                              output_data_dir=self.tmpdir)
            bugs_found.extend(data.get('bugs').keys())
        failed_bugs = [b for b in bugs.keys() if b not in bugs_found]
        if failed_bugs:
            if len(failed_bugs) == len(bugs):
                print("\nNone of the bugs were found!\n")
            else:
                print("\nThe following bug(s) were not found:\n")
                for bug_num in failed_bugs:
                    print(bug_num)
        self.assertEqual([], failed_bugs)

    def test_date_passing(self):
        options_parser = OptionsParser()
        input_str1 = "1 Dec 80"
        response1 = options_parser.date_parse(input_str1)
        input_str2 = "1_Dec_80"
        response2 = options_parser.date_parse(input_str2)
        correct_response = datetime(1980, 12, 1, 0, 0, tzinfo=pytz.utc)
        self.assertEqual(response1, response2, correct_response)

    def test_catch_all_bug_works(self):
        cli = self.populate_cli_var("fake_bug_03_database.yml")
        analysis = CrudeAnalysis(cli)
        self.assertIn('fake_bug_03', analysis.test_catalog.bugs)
'''
