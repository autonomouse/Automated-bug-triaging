from common_test_methods import CommonTestMethods
from doberman.common.common import Common


class CommonMethodsTests(CommonTestMethods):

    def test_join_dicts(self):
        old_dict = {'pipeline1': {'bug3': {'g': 'g',
                                           'h': 'h',
                                           'i': 'i',},},
                    'pipeline2': {'bug4': {'j': 'j',
                                           'k': 'k',
                                           'l': 'l',},}}

        new_dict = {'pipeline1': {'bug1': {'a': 'a',
                                           'b': 'b',
                                           'c': 'c',},
                                  'bug2': {'d': 'd',
                                           'e': 'e',
                                           'f': 'f',},}}

        gooddict = {'pipeline1': {'bug1': {'a': 'a',
                                           'b': 'b',
                                           'c': 'c',},
                                  'bug2': {'d': 'd',
                                           'e': 'e',
                                           'f': 'f',},
                                  'bug3': {'g': 'g',
                                           'h': 'h',
                                           'i': 'i',},},
                    'pipeline2': {'bug4': {'j': 'j',
                                           'k': 'k',
                                           'l': 'l',},}}
        testdict = Common().join_dicts(old_dict, new_dict)
        self.assertEqual(gooddict, testdict)
