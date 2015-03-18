#! /usr/bin/env python2

from doberman.analysis.analysis import CLI
from doberman.common import utils


class CLI(CLI):
    def __init__(self):
        self.set_up_log_and_parser()
        self.add_refinery_specific_options_to_parser()
        self.parse_cli_args()

    def add_refinery_specific_options_to_parser(self):
        prsr = self.parser
        prsr.add_option('-m', '--multibug', action='store', dest='multibugppl',
                        default=None, help=('jenkins job names with multiple' +
                                            ' jobs per pipeline (must be in ' +
                                            'quotes, seperated by spaces)'))
        prsr.add_option('-g', '--genoilstats_build', action='store', 
                        dest='genoilstats_build', default=None, 
                        help=('the jenkins build number of gen_oil_stats'))
        (opts, args) = self.parser.parse_args()

        # cli override of config values
        if opts.configfile:
            cfg = utils.get_config(opts.configfile)
        else:
            cfg = utils.get_config()

        if opts.multibugppl:
            multi_bugs_in_pl = opts.multibugppl
        else:
            multi_bugs_in_pl = cfg.get('DEFAULT', 'multi_bugs_in_pl')
        self.multi_bugs_in_pl = multi_bugs_in_pl.split(' ')

        if opts.genoilstats_build:
            self.genoilstats_build = opts.genoilstats_build
