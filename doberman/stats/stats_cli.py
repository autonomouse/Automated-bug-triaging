from doberman.common.CLI import CLI
from doberman.common.options_parser import OptionsParser
from doberman.common import utils


_config = utils.get_config()

JENKINS_URL = _config.get('DEFAULT', 'jenkins_url')
ENVIRONMENT = _config.get('DEFAULT', 'environment')
NETLOC = _config.get('DEFAULT', 'netloc')


class CLI(CLI):
    def __init__(self):
        self.set_up_parser()
        self.add_options_to_parser()
        self.add_stats_specific_options_to_parser()

    def populate_cli(self):
        options_parser = OptionsParser('doberman.stats')
        return options_parser.parse_opts_and_args(self.opts, self.args)

    def add_stats_specific_options_to_parser(self):
        prsr = self.parser
        prsr.add_option('-H', '--host', action='store', dest='host',
                        default=JENKINS_URL,
                        help="URL to Jenkins host. Default: " + JENKINS_URL)
        prsr.add_option('-N', '--nosummary', action='store_false',
                        dest='summary', default=True,
                        help='Disable printing summary output')
        prsr.add_option('-t', '--triage', action='store_true', dest='triage',
                        default=False,
                        help='Dump info on failed jobs for triage')
        (self.opts, self.args) = self.parser.parse_args()


class OptionsParser(OptionsParser):

    def parse_opts_and_args(self, opts, args=None):
        super(OptionsParser, self).parse_opts_and_args(opts, args)

        # cli override of config values
        if opts.configfile:
            cfg = utils.get_config(opts.configfile)
        else:
            cfg = utils.get_config()

        self.jenkins_host = None
        if opts.host:
            self.jenkins_host = opts.host
        else:
            self.jenkins_host = cfg.get('DEFAULT', 'jenkins_url')

        self.summary = True if opts.summary else False

        self.triage = True if opts.triage else False

        if opts.report_dir:
            self.reportdir = opts.report_dir
        else:
            self.reportdir = cfg.get('DEFAULT', 'analysis_report_dir')

        return self
