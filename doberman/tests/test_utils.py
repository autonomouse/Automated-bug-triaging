import testtools

from doberman.common import utils

class DobermanTestBase(testtools.TestCase):
    def setUp(self):
        super(DobermanTestBase, self).setUp()
        utils._config = []

    
