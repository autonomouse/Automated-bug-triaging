from doberman.common.CLI import CLI
from doberman.common.options_parser import OptionsParser
from doberman.common import utils


class CLI(CLI):
    def __init__(self):
        self.set_up_parser()
        self.add_options_to_parser()
        self.add_weebl_specific_options_to_parser()
        self.LOG = self.set_up_logger('analysis')

    def populate_cli(self):
        options_parser = OptionsParser()
        return options_parser.parse_opts_and_args(self.opts, self.args)

    def add_weebl_specific_options_to_parser(self):
        prsr = self.parser
        prsr.add_option('-w', '--weebl_ip', action='store', dest='weebl_ip',
                        default='http://10.245.0.14',
                        help=('IP address of the weebl server'))
        prsr.add_option('-a', '--auth', action='store',
                        dest='weebl_auth', default=None,
                        help=('Auth creds for weebl - username and password'))
        (self.opts, self.args) = self.parser.parse_args()


class OptionsParser(OptionsParser):

    def parse_opts_and_args(self, opts, args=None):
        super(OptionsParser, self).parse_opts_and_args(opts, args)

        # cli override of config values
        if opts.configfile:
            cfg = utils.get_config(opts.configfile)
        else:
            cfg = utils.get_config()

        if opts.weebl_ip:
            self.weebl_ip = opts.weebl_ip
        else:
            self.weebl_ip = cfg.get('DEFAULT', 'weebl_ip')

        if opts.weebl_auth:
            weebl_auth = opts.weebl_auth
        else:
            weebl_auth = cfg.get('DEFAULT', 'weebl_auth')
        self.weebl_auth = tuple(weebl_auth.split(' '))

        return self
