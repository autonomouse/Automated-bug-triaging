from doberman.tests.test_utils import DobermanTestBase
from doberman.analysis import analysis

class AddToYamlTest(DobermanTestBase):
    def setUp(self):
        super(DobermanTestBase, self).setUp()
        # Example data:
        self.pipeline = '452691cd-7dc5-4185-adef-2715e94df079'
        self.build = '17118'
        self.build_status = 'FAILURE'
        self.link = 'http://oil-jenkins.canonical.com/job/pipeline_deploy/17118/console'
        self.bug = {'bug_num': {'units': ['sm15k'], 
                                'regexps': {'console.txt': {'regexp': ['RE']}}, 
                                'vendors': ['nova-compute/0'], 
                                'additional info': {'text': '', 
                                                    'target file': 'console'}, 
                                'machines': ['hayward-28.oil']}}
        
    def test_no_bugs(self):
        matching_bugs = {}        
        output = analysis.add_to_yaml(self.pipeline, self.build, matching_bugs,
                                      self.build_status, self.link)
        self.assertTrue(output == {'pipeline': {}})
        
    def test_bug_matched(self):
        matching_bugs = self.bug       
        output = analysis.add_to_yaml(self.pipeline, self.build, matching_bugs,
                                      self.build_status, self.link)
        
        regexp = {'console.txt': {'regexp': ['RE']}}
        info = {'text': '', 'target file': 'console'}
        inner_dict = {'status': 'FAILURE',
                      'link to jenkins': self.link,
                      'build': self.build,
                      'bugs': {'bug_num': {'units': ['sm15k'],
                                           'regexps': regexp,
                                           'vendors': ['nova-compute/0'],
                                           'machines': ['hayward-28.oil'],
                                           'additional info': info}}}  
        

        desired_output = {'pipeline': {self.pipeline: inner_dict}}
        self.assertTrue(output == desired_output)

class PipelineCheckTest(DobermanTestBase): 
    def setUp(self):
        super(DobermanTestBase, self).setUp()
        self.correct_pipeline = '452691cd-7dc5-4185-adef-2715e94df079'
        self.incorrect_pipeline = '452-691c-d7dc5-185adef2715e94df07-9'
          
    def test_good_pipeline(self):
        self.assertTrue(analysis.pipeline_check(self.correct_pipeline))
          
    def test_bad_pipeline(self):
        self.assertFalse(analysis.pipeline_check(self.incorrect_pipeline))


class JoinDictsTest(DobermanTestBase):       
    def test_empty_dicts_join(self):
        old_dict = {}
        new_dict = {}
        output = analysis.join_dicts(old_dict, new_dict)        
        self.assertTrue(output == {})
           
    def test_dicts_join(self):
        old_dict = {'a':1}
        new_dict = {'b':2}
        output = analysis.join_dicts(old_dict, new_dict)        
        self.assertTrue(output == {'a': 1, 'b': 2})
           
    def test_dicts_join(self):
        old_dict = {'a':1}
        new_dict = {}
        output = analysis.join_dicts(old_dict, new_dict)        
        self.assertFalse(output == {'b': 2})
