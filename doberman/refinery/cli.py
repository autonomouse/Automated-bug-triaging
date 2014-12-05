#! /usr/bin/env python2

from doberman.analysis.analysis import CLI


class CLI(CLI):
    def __init__(self):
        self.set_up_log_and_parser()
        self.add_refinery_specific_options_to_parser()
        self.parse_cli_args()

    def add_refinery_specific_options_to_parser(self):
        prsr = self.parser
        prsr.add_option('-f', '--offline', action='store_true',
                        dest='offline_mode', default=False,
                        help='Offline mode must provide a local path using -o')

        (opts, args) = self.parser.parse_args()
        self.offline_mode = opts.offline_mode
