#! /usr/bin/env python2

from doberman.refinery.cli import CLI


class CLI(CLI):
    def __init__(self):
        self.set_up_log_and_parser()
        self.add_refinery_specific_options_to_parser()
        self.add_filing_station_specific_options_to_parser()
        self.parse_cli_args()

    def add_filing_station_specific_options_to_parser(self):
        prsr = self.parser
        prsr.add_option('-l', '--launchpad', action='store_true',
                        dest='autofile_on_launchpad', default=False,
                        help='Automatically file bug on launchpad')

        (opts, args) = self.parser.parse_args()
        self.autofile_on_launchpad = opts.autofile_on_launchpad
