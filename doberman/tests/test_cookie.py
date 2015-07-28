from common_test_methods import CommonTestMethods
from mock import patch, MagicMock


class DobermanTestCookies(CommonTestMethods):
    def test_import_pycookiecheat(self):
        exception = False
        try:
            from doberman.common import pycookiecheat
        except Exception:
            exception = True
        self.assertFalse(exception)

    def test_use_cookie_pysid(self):
        cli = self.populate_cli_var("blank_database.yml")
        cli.pysid = 'afafafafafafafafafafafafafafafaf'
        with patch('jenkinsapi.jenkins.Jenkins.__init__',
                   MagicMock(return_value=None)) as mocked_jenkins:
            from doberman.analysis.crude_jenkins import Jenkins
            jenkins = Jenkins(cli)
            jenkins.connect_to_jenkins()
            mocked_jenkins.assert_called_with(baseurl=cli.jenkins_host,
                                              cookies={'pysid': cli.pysid},
                                              netloc=cli.netloc)
