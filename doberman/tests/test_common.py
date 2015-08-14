from common_test_methods import CommonTestMethods
from doberman.common.base import DobermanBase


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
        testdict = DobermanBase().join_dicts(old_dict, new_dict)
        self.assertEqual(gooddict, testdict)

    def test_join_bad_dicts(self):
        old_dict = {'pipeline1': {'bug3': {'g': 'g',
                                           'h': 'h',
                                           'i': 'i',},},
                    'pipeline2': {'bug4': {'j': 'j',
                                           'k': 'k',
                                           'l': 'l',},}}

        new_dict1 = {}
        new_dict2 = None

        gooddict = {'pipeline1': {'bug3': {'g': 'g',
                                           'h': 'h',
                                           'i': 'i',},},
                    'pipeline2': {'bug4': {'j': 'j',
                                           'k': 'k',
                                           'l': 'l',},}}
        testdict1 = DobermanBase().join_dicts(old_dict, new_dict1)
        self.assertEqual(gooddict, testdict1)
        testdict2 = DobermanBase().join_dicts(old_dict, new_dict2)
        self.assertEqual(gooddict, testdict2)
        testdict2 = DobermanBase().join_dicts(None, None)
        self.assertEqual({}, testdict2)
