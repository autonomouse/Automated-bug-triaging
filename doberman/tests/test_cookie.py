from doberman.tests.test_utils import DobermanTestBase

class DobermanTestCookies(DobermanTestBase):
    def test_import_pycookiecheat(self):
        exception = False
        try:
            from doberman.common import pycookiecheat
        except Exception:
            exception = True
        self.assertFalse(exception)
