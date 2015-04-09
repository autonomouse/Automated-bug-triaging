from doberman.common.CLI import CLI
from doberman.common.options_parser import OptionsParser


class CLI(CLI):
    def __init__(self):
        self.set_up_parser()
        self.add_options_to_parser()
        self.add_filing_station_specific_options_to_parser()
        self.LOG = self.set_up_logger('filing_station')

    def populate_cli(self):
        options_parser = OptionsParser()
        return options_parser.parse_opts_and_args(self.opts, self.args)

    def add_filing_station_specific_options_to_parser(self):
        prsr = self.parser
        prsr.add_option('-l', '--launchpad', action='store_true',
                        dest='autofile_on_launchpad', default=False,
                        help='Automatically file bug on launchpad')

        (self.opts, self.args) = self.parser.parse_args()

class OptionsParser(OptionsParser):

    def parse_opts_and_args(self, opts, args=None):
        super(OptionsParser, self).parse_opts_and_args(opts, args)
        self.autofile_on_launchpad = opts.autofile_on_launchpad
        return self



