import testtools
from weebl_client.weebl_python2.weebl import Weebl


def generate_random_string(n=10, uppercase=False):
    ascii = string.ascii_uppercase if uppercase else string.ascii_lowercase
    return "".join(random.choice(ascii) for i in range(n))


class WeeblClientTests(testtools.TestCase):

    def test_munge_bug_info_data(self):

        uuid = 'MOCK-UUID'
        env_name = 'testing'
        self.weebl = Weebl(uuid, env_name)
        known_bug_regex_instances = [
            {'regex': "regex1",
             'uuid': 'regex1uuid',
             'target_file_globs': ['tempest_xunit.xml'], 'bug': 'bug_uuid1'},
            {'regex': 'regex2',
             'uuid': 'regex2uuid',
             'target_file_globs': ['console.txt'], 'bug': 'bug_uuid2'}]
        bug_instances = [
            {'uuid': 'bug_uuid1',
             'description': None,
             'summary': 'bug instance 1 summary',
             'bug_tracker_bugs': ['lp_bug_01'], },
            {'uuid': 'bug_uuid2',
             'description': None,
             'summary': 'bug instance 2 summary',
             'bug_tracker_bugs': ['lp_bug_02'], }]
        bug_tracker_bug_instances = [{'bug_id':'lp_bug_01'},
                                     {'bug_id':'lp_bug_02'},]
        target_file_glob = [{'glob_pattern': 'console.txt',
                             'job_types': ['pipeline_deploy',
                                           'pipeline_prepare',
                                           'smoke_tempest_test', ], },
                             {'glob_pattern': 'tempest_xunit.xml',
                             'job_types': ['smoke_tempest_test'], }, ]
        output = self.weebl.munge_bug_info_data(known_bug_regex_instances,
            bug_instances, bug_tracker_bug_instances, target_file_glob)
        correct_output = {'bugs':
            {'bug1': {'affects': [],
                      'category': [],
                      'description': '',
                      'smoke_tempest_test': [
                          {'tempest_xunit.xml': {'regexp': ['regex1']}}]},
             'bug2': {'affects': [],
                      'category': [],
                      'description': '',
                      'pipeline_deploy': [
                          {'console.txt': {'regexp': ['regex2']}}],
                      'pipeline_prepare': [
                          {'console.txt': {'regexp': ['regex2']}}],
                      'smoke_tempest_test': [
                          {'console.txt': {'regexp': ['regex2']}}]}}}
        self.assertEqual(correct_output, output)
