import json
import pytz
import socket
import urlparse
import parsedatetime as pdt
from datetime import datetime
from dateutil.parser import parse
from doberman.common import utils
from doberman.__init__ import __version__
from ConfigParser import NoOptionError


class OptionsParser(object):

    def __init__(self, log_as='doberman.analysis'):
        self.LOG = utils.get_logger(log_as)

    def parse_opts_and_args(self, opts, args=None):
        """ A method to parse opts and args (from whatever source, CLI, tests
            or even a GUI should someone wish to code one) and replace the
            values in the config file.
        """
        self.LOG.info("Doberman version {0}".format(__version__))
        ts_format = '%a %d %b %Y %H:%M:%S'

        # cli override of config values
        if opts.configfile:
            cfg = utils.get_config(opts.configfile)
        else:
            cfg = utils.get_config()

        self.external_jenkins_url = cfg.get('DEFAULT', 'external_jenkins_url')
        self.match_threshold = cfg.get('DEFAULT', 'match_threshold')
        self.crude_job = cfg.get('DEFAULT', 'crude_job')

        self.max_sequence_size = cfg.get('DEFAULT', 'max_sequence_size')
        self.generic_bug_id = cfg.get('DEFAULT', 'generic_bug_id')
        self.bug_tracker_url = cfg.get('DEFAULT', 'bug_tracker_url')

        self.offline_mode = opts.offline_mode

        self.database = opts.database
        self.LOG.info("database=%s" % self.database)
        # database filepath might be set in config
        if self.database is None:
            self.LOG.info('getting DB from config file')
            self.database = cfg.get('DEFAULT', 'database_uri')
            self.LOG.info('database=%s' % self.database)

        self.dont_replace = True

        if opts.use_deploy:
            self.use_deploy = opts.use_deploy
        else:
            self.use_deploy = cfg.get('DEFAULT', 'use_deploy').lower() in \
                ['true', 'yes']

        if opts.jobnames:
            job_names = opts.jobnames
        else:
            job_names = cfg.get('DEFAULT', 'job_names')
        self.job_names = job_names.split(' ')

        self.pysid = opts.pysid

        if opts.jenkins_host:
            self.jenkins_host = opts.jenkins_host
        else:
            self.jenkins_host = cfg.get('DEFAULT', 'jenkins_url')

        # cli wins, then config, otherwise default to True
        if opts.verbose:
            self.reduced_output_text = False
        else:
            try:
                vrbs = cfg.get('DEFAULT', 'verbose').lower() in ['true', 'yes']
                reduced = False if vrbs else True
                self.reduced_output_text = reduced
            except:
                self.reduced_output_text = True

        # cli wins, then config, then hostname lookup
        netloc_cfg = cfg.get('DEFAULT', 'netloc')
        if opts.netloc:
            self.netloc = opts.netloc
        elif netloc_cfg not in ['None', 'none', None]:
            self.netloc = netloc_cfg
        else:
            self.netloc = socket.gethostbyname(urlparse.urlsplit(
                                               opts.jenkins_host).netloc)

        if opts.run_remote:
            self.run_remote = opts.run_remote
        else:
            self.run_remote = \
                cfg.get('DEFAULT', 'run_remote').lower() in ['true', 'yes']

        if opts.report_dir:
            self.reportdir = opts.report_dir
        else:
            self.reportdir = cfg.get('DEFAULT', 'analysis_report_dir')

        if opts.keep_data:
            self.keep_data = opts.keep_data
        else:
            self.keep_data = \
                cfg.get('DEFAULT', 'keep_data').lower() in ['true', 'yes']

        # cli wins, then config, then just call it 'Unknown':
        environment = cfg.get('DEFAULT', 'environment')
        if opts.environment:
            self.environment = opts.environment
        elif environment not in ['None', 'none', None]:
            self.environment = environment
        else:
            self.environment = "Unknown"

        # WEEBL
        try:
            use_weebl = cfg.get('DEFAULT', 'use_weebl').lower() in ['true',
                                                                    'yes']
        except NoOptionError:
            pass
        if opts.use_weebl:
            self.use_weebl = opts.use_weebl
        elif use_weebl:
            self.use_weebl = use_weebl
        else:
            self.use_weebl = False

        if opts.weebl_url:
            self.weebl_url = opts.weebl_url
        else:
            self.weebl_url = cfg.get('DEFAULT', 'weebl_url')

        if self.use_weebl is True:
            if opts.weebl_username:
                self.weebl_username = opts.weebl_username
            else:
                self.weebl_username = cfg.get('DEFAULT', 'weebl_username')
            if opts.weebl_apikey:
                self.weebl_apikey = opts.weebl_apikey
            else:
                self.weebl_apikey = cfg.get('DEFAULT', 'weebl_apikey')
        #

        self.logpipelines = True if opts.logpipelines else False

        try:
            dont_scan = cfg.get('DEFAULT', 'dont_scan').split(' ')
        except Exception:
            dont_scan = []
        self.dont_scan = tuple(dont_scan)

        # cli wins, then config, otherwise default to True
        if opts.unverified:
            self.verify = False
        else:
            try:
                vrfy = cfg.get('DEFAULT', 'verify').lower() in ['true', 'yes']
                self.verify = vrfy
            except:
                self.verify = True

        if opts.xmls:
            xmls = opts.xmls
        else:
            xmls = cfg.get('DEFAULT', 'multi_bug_stats_files')
        self.xmls = xmls.replace(' ', '').split(',')

        if self.jenkins_host in [None, 'None', 'none', '']:
            self.LOG.error("Missing jenkins configuration")
            raise Exception("Missing jenkins configuration")

        self.testframework_version = opts.testframework_version

        if (not opts.start) and (not opts.end):
            if not set(args):
                opts.start = '24 hours ago'
                msg = "No pipeline IDs provided, defaulting to past 24 hours"
                self.LOG.info(msg)

        # Unique identifier of environment:
        uuid = cfg.get('DEFAULT', 'environment_uuid')
        if opts.uuid:
            self.uuid = opts.uuid
        elif uuid is None:
            self.uuid = None
        else:
            self.uuid = uuid

        # Start and end datetimes:
        if opts.start or opts.end:
            if self.use_deploy:
                err_msg = "Cannot use deploy build numbers AND a date range. "
                err_msg += "Aborting."
                self.LOG.error(err_msg)
                raise Exception(err_msg)
            else:
                self.use_date_range = True
                if not opts.start:
                    self.start = self.date_parse('24 hours ago')
                    self.LOG.info("Defaulting to a start date of 24 hours ago")
                else:
                    self.start = self.date_parse(opts.start)
                    stmsg = "Using a start date of {0}"
                    self.LOG.info(stmsg.format(self.start.strftime(ts_format)))
                if not opts.end:
                    self.end = datetime.utcnow()
                    self.LOG.info("Defaulting to an end date of 'now' ({})"
                                  .format(self.end.strftime(ts_format)))
                else:
                    self.end = self.date_parse(opts.end)
                    stmsg = "Using an end date of {0}"
                    self.LOG.info(stmsg.format(self.end.strftime(ts_format)))
        else:
            self.use_date_range = False

        # Get arguments:
        self.ids = set(args)
        if not self.ids:
            if not self.use_date_range:
                raise Exception("No pipeline IDs provided")

        return self

    def date_parse(self, input_str):
        """Use two different strtotime functions to return a datetime
        object when possible.
        """
        string = input_str.replace('_', ' ')

        try:
            return pytz.utc.localize(parse(string))
        except:
            pass

        try:
            val = pdt.Calendar(pdt.Constants(usePyICU=False)).parse(string)
            if val[1] > 0:  # only do strict matching
                return pytz.utc.localize(datetime(*val[0][:6]))
        except:
            pass

        raise ValueError('Date format {0} not understood, try 2014-02-12'
                         .format(string))
