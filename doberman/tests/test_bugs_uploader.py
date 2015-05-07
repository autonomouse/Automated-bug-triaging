import os
import yaml
from common_test_methods import CommonTestMethods
from doberman.common.upload_bugs_from_mock_to_db import get_new_or_bugs_to_edit


class BugsUploader(CommonTestMethods):
    def setUp(self):
        super(BugsUploader, self).setUp()
        db_files_dir = 'doberman/tests/mock_data/database_files'
        self.db_3_bugs = os.path.join(db_files_dir, 'blank_database.yml')
        self.db_4_bugs = os.path.join(db_files_dir, 'fake_bug_01_database.yml')
        self.db_4_bugs_alt = os.path.join(db_files_dir, 
                                          'fake_bug_02_database.yml')
        self.db_multi = os.path.join(db_files_dir, 
                                     'multiple_changes_database.yml')

    def tearDown(self):
        super(BugsUploader, self).tearDown()

    def test_same(self):
        with open(self.db_4_bugs, 'r') as f:
            local_db = yaml.load(f)
        altered_bugs, orphan_bugs = get_new_or_bugs_to_edit(local_db, local_db)
        self.assertTrue(altered_bugs == [])
        self.assertTrue(orphan_bugs == [])

    def test_bug_added(self):
        with open(self.db_3_bugs, 'r') as f1:
            remote_db = yaml.load(f1)
        with open(self.db_4_bugs, 'r') as f2:
            local_db = yaml.load(f2)
        altered_bugs, orphan_bugs = get_new_or_bugs_to_edit(local_db, 
                                                            remote_db)
        self.assertTrue(altered_bugs == ['fake_bug_01'])

    def test_bug_removed(self):
        with open(self.db_4_bugs, 'r') as f1:
            remote_db = yaml.load(f1)
        with open(self.db_3_bugs, 'r') as f2:
            local_db = yaml.load(f2)
        altered_bugs, orphan_bugs = get_new_or_bugs_to_edit(local_db, 
                                                            remote_db)
        newly_added = [('fake_bug_01', {'category': 'None', 'description': 
                       'A fake bug for testing purposes', 'pipeline_deploy': 
                       [{'console.txt': {'regexp': 
                       ['mv run_config artifacts/run_config.parameter']}}]})]
        self.assertTrue(orphan_bugs == newly_added)

    def test_bug_changed(self):
        with open(self.db_4_bugs, 'r') as f1:
            remote_db = yaml.load(f1)
        with open(self.db_4_bugs_alt, 'r') as f2:
            local_db = yaml.load(f2)
        altered_bugs, orphan_bugs = get_new_or_bugs_to_edit(local_db, 
                                                            remote_db)
        self.assertTrue(altered_bugs == ['fake_bug_01'])

        
    def test_add_remove_changed(self):
        with open(self.db_4_bugs, 'r') as f1:
            remote_db = yaml.load(f1)
        with open(self.db_multi, 'r') as f2:
            local_db = yaml.load(f2)
        altered_bugs, orphan_bugs = get_new_or_bugs_to_edit(local_db, 
                                                            remote_db)
        newly_added = [('0000000', {'category': 'None', 'pipeline_prepare': 
                       [{'console.txt': {'regexp': 
                       ["this line of text really shouldn't be in there"]}}], 
                       'pipeline_deploy': [{'console.txt': {'regexp': 
                       ["this line of text really shouldn't be in there"]}}], 
                       'description': 'test bug', 'test_tempest_smoke': 
                       [{'console.txt': {'regexp': 
                       ["this line of text really shouldn't be in there"]}}]})]
        self.assertTrue(orphan_bugs == newly_added)
        self.assertTrue(altered_bugs == ['fake_bug_01', 'fake_bug_02'])
        
