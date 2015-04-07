#! /usr/bin/env python2

import sys
import os
import socket
import urlparse
import shutil
import optparse
import json
import pytz
import parsedatetime as pdt
from dateutil.parser import parse
from datetime import datetime
from doberman.common import utils
from jenkinsapi.custom_exceptions import *
from doberman.common.common import Common
from crude_jenkins import Jenkins, Deploy, Prepare, Tempest
from crude_test_catalog import TestCatalog
from doberman.__init__ import __version__


class CrudeAnalysis(Common):
    """

    """

    def __init__(self):
        self.cli = CLI()
        self.jenkins = Jenkins(self.cli)
        self.test_catalog = TestCatalog(self.cli)
        self.build_numbers = self.build_pl_ids_and_check()
        self.pipeline_processor(self.build_numbers)
        self.remove_dirs(self.cli.job_names)

    def build_pl_ids_and_check(self):
        self.pipeline_ids = []
        self.ids = self.cli.ids

        if self.cli.offline_mode:
            self.cli.LOG.info(" *** Offline mode *** ")
            build_numbers = self.test_catalog.get_pipelines_from_paabn()
            self.ids = build_numbers.keys()

        elif self.cli.use_deploy:
            # If using build numbers instead of pipelines, get pipeline:
            msg = "Looking up pipeline ids for the following jenkins "
            msg += "pipeline_deploy build numbers: %s"
            self.cli.LOG.info(msg % ", ".join([str(i) for i in self.cli.ids]))

            # Expand out id numbers if a range has been used:
            exp_ids = []
            for idn in self.ids:
                if '-' in idn:
                    range_start = int(idn.split('-')[0])
                    range_end = int(idn.split('-')[-1]) + 1
                    exp_range = [str(b) for b in range(range_start, range_end)]
                    exp_ids.extend(exp_range)
                else:
                    exp_ids.append(idn)
            self.ids = set(exp_ids)

        elif self.cli.use_date_range:
            # If using a date range instead of pipelines, get pipeline:
            msg = "Getting pipeline ids for between {0} and {1} (this locale)"
            self.cli.LOG.info(msg.format(self.cli.start.strftime('%c'),
                                         self.cli.end.strftime('%c')))
            self.ids = self.test_catalog.get_pipelines_from_date_range()

        for pos, idn in enumerate(self.ids):
            if self.cli.use_deploy:
                pipeline = self.jenkins.get_pipeline_from_deploy_build(idn)
            else:
                pipeline = idn
            # Quickly cycle through to check all pipelines are real:
            if not self.jenkins.pipeline_check(pipeline):
                msg = "Pipeline ID \"%s\" is an unrecognised format" % pipeline
                self.cli.LOG.error(msg)
            else:
                self.pipeline_ids.append(pipeline)

            # Notify user of progress:
            pgr = self.calculate_progress(pos, self.ids)
            if pgr:
                self.cli.LOG.info("Pipeline lookup {0}% complete.".format(pgr))
        msg = "Pipeline lookup 100% complete: All pipelines checked. "
        msg += "Now polling jenkins and processing data."
        self.cli.LOG.info(msg)
        return self.test_catalog.get_all_pipelines(self.pipeline_ids)

    def remove_dirs(self, folders_to_remove):
        """ Remove data folders used to store untarred artifacts (just leaving
            yaml files).

        """

        if type(folders_to_remove) not in [list, tuple, dict]:
            folders_to_remove = [folders_to_remove]

        if not self.cli.keep_data:
            for folder in folders_to_remove:
                kill_me = os.path.join(self.cli.reportdir, folder)
                if os.path.isdir(kill_me):
                    shutil.rmtree(kill_me)

    def pipeline_processor(self, build_numbers):

        self.message = 1
        deploy_yamldict = {}
        prepare_yamldict = {}
        tempest_yamldict = {}
        problem_pipelines = []

        for pipeline_id in self.pipeline_ids:
            deploy_dict = {}
            prepare_dict = {}
            tempest_dict = {}
            self.pipeline = pipeline_id
            try:
                # Get pipeline data then process each:
                deploy_build = build_numbers[pipeline_id]['pipeline_deploy']
                prepare_build = build_numbers[pipeline_id]['pipeline_prepare']
                tempest_build = \
                    build_numbers[pipeline_id]['test_tempest_smoke']

                # Pull console and artifacts from jenkins:
                deploy = Deploy(deploy_build, 'pipeline_deploy', self.jenkins,
                                deploy_dict, self.cli,
                                self.test_catalog.bugs, pipeline_id)
                deploy_dict = deploy.yaml_dict
                self.message = deploy.message

                if prepare_build:
                    prepare = Prepare(prepare_build, 'pipeline_prepare',
                                      self.jenkins, prepare_dict,
                                      self.cli, self.test_catalog.bugs,
                                      pipeline_id, deploy)
                    prepare_dict = prepare.yaml_dict
                    if self.message != 1:
                        self.message = prepare.message

                if tempest_build:
                    tempest = Tempest(tempest_build, 'test_tempest_smoke',
                                      self.jenkins, tempest_dict,
                                      self.cli, self.test_catalog.bugs,
                                      pipeline_id, prepare)
                    tempest_dict = tempest.yaml_dict
                    if self.message != 1:
                        self.message = tempest.message

            except Exception as e:
                if 'deploy_build' not in locals():
                    msg = "Cannot acquire pipeline deploy build number"
                    msg += " (may be cookie related?)"
                else:
                    probmsg = "Problem with {} - skipping "
                    if deploy_build:
                        probmsg += "(deploy_build: {})"
                    self.cli.LOG.error(probmsg.format(pipeline_id,
                                                      deploy_build))
                    problem_pipelines.append((pipeline_id, deploy_build, e))
                self.cli.LOG.exception(e)

            pl_proc_msg = "CrudeAnalysis has finished processing pipline id: "
            pl_proc_msg += "{0} and is returning a value of {1}."
            self.cli.LOG.info(pl_proc_msg.format(pipeline_id, self.message))

            # Merge dictionaries (necessary for multiple pipelines):
            deploy_yamldict['pipeline'] = \
                self.join_dicts(deploy_yamldict.get('pipeline', {}),
                                deploy_dict.get('pipeline', {}))
            prepare_yamldict['pipeline'] = \
                self.join_dicts(prepare_yamldict.get('pipeline', {}),
                                prepare_dict.get('pipeline', {}))
            tempest_yamldict['pipeline'] = \
                self.join_dicts(tempest_yamldict.get('pipeline', {}),
                                tempest_dict.get('pipeline', {}))

        # Export to yaml:
        rdir = self.cli.reportdir
        self.export_to_yaml(deploy_yamldict, 'pipeline_deploy', rdir)
        self.export_to_yaml(prepare_yamldict, 'pipeline_prepare', rdir)
        self.export_to_yaml(tempest_yamldict, 'test_tempest_smoke', rdir)

        # Write to file any pipelines (+ deploy build) that failed processing:
        if not problem_pipelines == []:
            file_path = os.path.join(self.cli.reportdir,
                                     'problem_pipelines.yaml')
            open(file_path, 'a').close()  # Create file if doesn't exist yet
            with open(file_path, 'r+') as pp_file:
                existing_content = pp_file.read()
                pp_file.seek(0, 0)  # Put at beginning of file
                pp_file.write("\n" + str(datetime.now())
                              + "\n--------------------------\n")
                for problem_pipeline in problem_pipelines:
                    probs = "* %s (deploy build: %s):\n%s\n\n"
                    pp_file.write(probs % problem_pipeline)
                pp_file.write(existing_content)
                errmsg = "There were some pipelines that could not be "
                errmsg += "processed. This information was written to problem"
                errmsg += "_pipelines.yaml in " + self.cli.reportdir + "\n\n"
                self.cli.LOG.error(errmsg)

        self.log_pipelines()

    def export_to_yaml(self, yaml_dict, job, reportdir):
        """ Write output files. """
        filename = 'triage_' + job + '.yml'
        if not yaml_dict:
            yaml_dict['pipeline'] = {}
        self.write_output_yaml(reportdir, filename, yaml_dict)


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
        self.set_up_log_and_parser()
        self.parse_cli_args()

    def set_up_log_and_parser(self):
        self.LOG = utils.get_logger('doberman.analysis')
        self.LOG.info("Doberman version {0}".format(__version__))
        usage = "usage: %prog [options] pipeline_id1 pipeline_id2 ..."
        self.parser = optparse.OptionParser(usage=usage)
        self.add_options_to_parser()

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

    def parse_cli_args(self):
        (opts, args) = self.parser.parse_args()

        # cli override of config values
        if opts.configfile:
            cfg = utils.get_config(opts.configfile)
        else:
            cfg = utils.get_config()

        self.external_jenkins_url = cfg.get('DEFAULT', 'external_jenkins_url')
        self.match_threshold = cfg.get('DEFAULT', 'match_threshold')
        self.crude_job = cfg.get('DEFAULT', 'crude_job')

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

        if opts.tc_host:
            self.tc_host = opts.tc_host
        else:
            self.tc_host = cfg.get('DEFAULT', 'oil_api_url')

        if opts.keep_data:
            self.keep_data = opts.keep_data
        else:
            self.keep_data = \
                cfg.get('DEFAULT', 'keep_data').lower() in ['true', 'yes']

        self.logpipelines = True if opts.logpipelines else False

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
            xmls = cfg.get('DEFAULT', 'xmls_to_defer')
        self.xmls = xmls.replace(' ', '').split(',')

        if self.jenkins_host in [None, 'None', 'none', '']:
            self.LOG.error("Missing jenkins configuration")
            raise Exception("Missing jenkins configuration")

        if self.tc_host in [None, 'None', 'none', '']:
            self.LOG.error("Missing test-catalog configuration")
            raise Exception("Missing test-catalog configuration")

        # Cookie for test-catalog:
        tc_auth = cfg.get('DEFAULT', 'tc_auth')
        try:
            self.tc_auth = json.load(open(tc_auth))
        except:
            msg = "Cannot find cookie for test-catalog: %s" % tc_auth
            self.LOG.error(msg)
            raise Exception(msg)
        self.LOG.debug('tc_auth token=%s' % self.tc_auth)

        if (not opts.start) and (not opts.end):
            if not set(args):
                opts.start = '24 hours ago'
                msg = "No pipeline IDs provided, defaulting to past 24 hours"
                self.LOG.info(msg)

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
                    self.LOG.info(stmsg.format(self.start.strftime('%c')))
                if not opts.end:
                    self.end = datetime.utcnow()
                    self.LOG.info("Defaulting to an end date of 'now'")
                else:
                    self.end = self.date_parse(opts.end)
                    stmsg = "Using an end date of {0}"
                    self.LOG.info(stmsg.format(self.end.strftime('%c')))
        else:
            self.use_date_range = False

        # Get arguments:
        self.ids = set(args)
        if not self.ids:
            if not self.use_date_range:
                raise Exception("No pipeline IDs provided")

    def date_parse(self, string):
        """Use two different strtotime functions to return a datetime
        object when possible.
        """
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


def main():
    crude = CrudeAnalysis()
    return crude.message


if __name__ == "__main__":
    sys.exit(main())
