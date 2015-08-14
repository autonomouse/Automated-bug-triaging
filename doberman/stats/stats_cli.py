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
        options_parser = OptionsParser(log_as='doberman.stats')
        return options_parser.parse_opts_and_args(self.opts, self.args)

    def add_stats_specific_options_to_parser(self):
        prsr = self.parser
        prsr.add_option('-H', '--host', action='store', dest='host',
                        default=JENKINS_URL,
                        help="URL to Jenkins host. Default: " + JENKINS_URL)
        prsr.add_option('-m', '--multibug', action='store', dest='multibugppl',
                        default=None, help=('jenkins job names with multiple' +
                                            ' jobs per pipeline (must be in ' +
                                            'quotes, seperated by spaces)'))
        prsr.add_option('-N', '--nosummary', action='store_false',
                        dest='nosummary', default=True,
                        help='Disable printing summary output')
        prsr.add_option('-t', '--triage', action='store_true', dest='triage',
                        default=False,
                        help='Dump info on failed jobs for triage')
        prsr.add_option('-S', '--subset_sr_jobs', action='store',
                        dest='subset_success_rate_jobs', default=None,
                        help=('jenkins job names to be included in subset ' +
                              'success rate calulation (must be in quotes, ' +
                              'seperated by spaces)'))
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

        self.summary = False if opts.nosummary else True

        if opts.multibugppl:
            multi_bugs_in_pl = opts.multibugppl
        else:
            multi_bugs_in_pl = cfg.get('DEFAULT', 'multi_bugs_in_pl')
        self.multi_bugs_in_pl = multi_bugs_in_pl.split(' ')

        self.triage = True if opts.triage else False

        if opts.report_dir:
            self.reportdir = opts.report_dir
        else:
            self.reportdir = cfg.get('DEFAULT', 'analysis_report_dir')

        if opts.subset_success_rate_jobs:
            subset_success_rate_jobs = opts.subset_success_rate_jobs
        else:
            subset_success_rate_jobs = cfg.get('DEFAULT',
                                               'subset_success_rate_jobs')
        if subset_success_rate_jobs is None:
            self.subset_success_rate_jobs = []
        else:
            self.subset_success_rate_jobs = subset_success_rate_jobs.split(' ')

        return self
