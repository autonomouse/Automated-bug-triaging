import optparse
from doberman.common.common import Common
from doberman.common.options_parser import OptionsParser
from doberman.common import utils
from doberman.__init__ import __version__


class CLI(Common):
    """ Command line interface for crude_analysis...

    Attributes:
        self.database:  A string representing the path to mock database or None
                        for a real DB...
        self.use_deploy:
        self.jenkins_host:
        self.run_remote:
        self.reportdir:
        self.tc_host:
        self.keep_data:
        self.xmls:
        self.ids:       A string or list of pipeline ids or deploy build
                        numbers...

    """

    def __init__(self):
        self.set_up_parser()
        self.add_options_to_parser()
        (self.opts, self.args) = self.parser.parse_args()

    def set_up_logger(self, module):
        LOG = utils.get_logger('doberman.{}'.format(module))
        LOG.info("Doberman version {0}".format(__version__))
        return LOG

    def populate_cli(self):
        options_parser = OptionsParser()
        return options_parser.parse_opts_and_args(self.opts, self.args)

    def set_up_parser(self):
        usage = "usage: %prog [options] pipeline_id1 pipeline_id2 ..."
        self.parser = optparse.OptionParser(usage=usage)

    def add_options_to_parser(self):
        prsr = self.parser
        prsr.add_option('-b', '--usebuildnos', action='store_true',
                        dest='use_deploy', default=False,
                        help='use pipeline_deploy build numbers not pipelines')
        prsr.add_option('-c', '--config', action='store', dest='configfile',
                        default=None,
                        help='specify path to configuration file')
        prsr.add_option('-d', '--dburi', action='store', dest='database',
                        default=None,
                        help='set URI to bug/regex db: /path/to/mock_db.yaml')
        prsr.add_option('-e', '--end', action='store', dest='end',
                        default=None, help='ending date string. Default = now')
        prsr.add_option('-f', '--offline', action='store_true',
                        dest='offline_mode', default=False,
                        help='Offline mode must provide a local path using -o')
        prsr.add_option('-i', '--jobnames', action='store', dest='jobnames',
                        default=None, help=('jenkins job names (must be in ' +
                                            'quotes, seperated by spaces)'))
        prsr.add_option('-J', '--jenkins', action='store', dest='jenkins_host',
                        default=None,
                        help='URL to Jenkins server')
        prsr.add_option('-k', '--keep', action='store_true', dest='keep_data',
                        default=False,
                        help='Do not delete extracted tarballs when finished')
        prsr.add_option('-n', '--netloc', action='store', dest='netloc',
                        default=None,
                        help='Specify an IP to rewrite URLs')
        prsr.add_option('-o', '--output', action='store', dest='report_dir',
                        default=None,
                        help='specific the report output directory')
        prsr.add_option('-p', '--logpipelines', action='store_true',
                        dest='logpipelines', default=False,
                        help='Record which pipelines were processed in a yaml')
        prsr.add_option('-r', '--remote', action='store_true',
                        dest='run_remote', default=False,
                        help='set if running analysis remotely')
        prsr.add_option('-s', '--start', action='store', dest='start',
                        default=None,
                        help='starting date string. Default: \'24 hours ago\'')
        prsr.add_option('-T', '--testcatalog', action='store', dest='tc_host',
                        default=None,
                        help='URL to test-catalog API server')
        prsr.add_option('-u', '--unverified', action='store_true',
                        dest='unverified', default=False,
                        help='set to allow unverified certificate requests')
        prsr.add_option('-v', '--verbose', action='store_true', dest='verbose',
                        default=False, help='Reduced text in output yaml.')
        prsr.add_option('-x', '--xmls', action='store', dest='xmls',
                        default=None,
                        help='XUnit files to parse as XML, not as plain text')
