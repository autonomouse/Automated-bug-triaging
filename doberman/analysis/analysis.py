#! /usr/bin/env python2

import sys
import os
import yaml
import socket
import urlparse
import shutil
import optparse
import datetime
import json
import special_cases
from doberman.common import utils
from jenkinsapi.custom_exceptions import *
from crude_common import Common
from crude_jenkins import Jenkins, Deploy, Prepare, Tempest
from crude_test_catalog import TestCatalog


class CrudeAnalysis(Common):
    """

    """

    job_names = ['pipeline_deploy', 'pipeline_prepare', 'test_tempest_smoke']

    def __init__(self):
        self.cli = CLI()
        self.jenkins = Jenkins(self.cli)
        self.test_catalog = TestCatalog(self.cli)
        self.build_pl_ids_and_check()
        self.pipeline_processor()
        self.remove_dirs()

    def build_pl_ids_and_check(self):

        self.pipeline_ids = []
        self.ids = self.cli.ids

        # If using build numbers instead of pipelines, get pipeline:
        if self.cli.use_deploy:
            msg = "Looking up pipeline ids for the following jenkins "
            msg += "pipeline_deploy build numbers: %s"
            self.cli.LOG.info(msg % ", ".join([str(i) for i in self.cli.ids]))
        self.calc_when_to_report()
        for pos, idn in enumerate(self.ids):
            if self.cli.use_deploy:
                pipeline = self.jenkins.get_pipeline_from_deploy_build(idn)
            else:
                pipeline = idn
            # Quickly cycle through to check all pipelines are real:
            if not self.jenkins.pipeline_check(pipeline):
                msg = "Pipeline ID \"%s\" is an unrecognised format" % pipeline
                self.cli.LOG.error(msg)
                raise Exception(msg)
            self.pipeline_ids.append(pipeline)

            # Notify user/log of progress
            progress = [round((pc / 100.0) * len(self.ids))
                        for pc in self.report_at]
            if pos in progress:
                pc = str(self.report_at[progress.index(pos)])
                self.cli.LOG.info("Pipeline lookup {0}% complete.".format(pc))
        self.cli.LOG.info("All pipelines checked. Now polling jenkins " +
                          "and processing data")

    def calc_when_to_report(self):
        """ Determine at what percentage completion to notify user of progress
            based on the number of entries in self.ids

        """

        if len(self.ids) > 35:
            self.report_at = range(5, 100, 5)  # Notify every 5 percent
        elif len(self.ids) > 25:
            self.report_at = range(10, 100, 10)  # Notify every 10 percent
        elif len(self.ids) > 10:
            self.report_at = range(25, 100, 25)  # Notify every 25 percent
        else:
            self.report_at = [50]  # Notify at 50 percent

    def remove_dirs(self):
        """ Remove data folders used to store untarred artifacts (just leaving
            yaml files).

        """

        if not self.cli.keep_data:
            for folder in self.job_names:
                kill_me = os.path.join(self.cli.reportdir, folder)
                if os.path.isdir(kill_me):
                    shutil.rmtree(kill_me)

    def pipeline_processor(self):
        deploy_yaml_dict = {}
        prepare_yaml_dict = {}
        tempest_yaml_dict = {}
        problem_pipelines = []

        for pipeline_id in self.pipeline_ids:
            self.pipeline = pipeline_id
            try:
                # Get pipeline data then process each:
                deploy_build, prepare_build, tempest_build = \
                    self.test_catalog.get_pipelines(pipeline_id)

                # Pull console and artifacts from jenkins:
                deploy = Deploy(deploy_build, 'pipeline_deploy', self.jenkins,
                                deploy_yaml_dict, self.cli,
                                self.test_catalog.bugs, pipeline_id)
                deploy_yaml_dict = deploy.yaml_dict

                if prepare_build and not deploy.still_running:
                    prepare = Prepare(prepare_build, 'pipeline_prepare',
                                      self.jenkins, prepare_yaml_dict,
                                      self.cli, self.test_catalog.bugs,
                                      pipeline_id, deploy)
                    prepare_yaml_dict = prepare.yaml_dict

                if tempest_build and not deploy.still_running:
                    tempest = Tempest(tempest_build, 'test_tempest_smoke',
                                      self.jenkins, tempest_yaml_dict,
                                      self.cli, self.test_catalog.bugs,
                                      pipeline_id, prepare)
                    tempest_yaml_dict = tempest.yaml_dict

                if deploy.still_running:
                    self.cli.LOG.error("%s is still running - skipping"
                                       % deploy_build)
            except:
                if 'deploy_build' not in locals():
                    msg = "Cannot acquire pipeline deploy build number"
                    msg += " (may be cookie related?)"
                    deploy_yaml_dict = \
                        self.non_db_bug(special_cases.bug_dict['pipeline_id'],
                                        deploy_yaml_dict, msg)
                else:
                    print("Problem with " + pipeline_id + " - skipping "
                          "(deploy_build:  " + deploy_build + ")")
                    problem_pipelines.append((pipeline_id, deploy_build))

        # Export to yaml:
        rdir = self.cli.reportdir
        self.export_to_yaml(deploy_yaml_dict, 'pipeline_deploy', rdir)
        self.export_to_yaml(prepare_yaml_dict, 'pipeline_prepare', rdir)
        self.export_to_yaml(tempest_yaml_dict, 'test_tempest_smoke', rdir)

        # Write to file any pipelines (+ deploy build) that failed processing:
        if not problem_pipelines == []:
            file_path = os.path.join(self.cli.reportdir,
                                     'problem_pipelines.yaml')
            open(file_path, 'a').close()  # Create file if doesn't exist yet
            with open(file_path, 'r+') as pp_file:
                existing_content = pp_file.read()
                pp_file.seek(0, 0)  # Put at beginning of file
                pp_file.write("\n" + str(datetime.datetime.now())
                              + "\n--------------------------\n")
                for problem_pipeline in problem_pipelines:
                    pp_file.write("%s (deploy build: %s)\n" % problem_pipeline)
                pp_file.write(existing_content)
                errmsg = "There were some pipelines that could not be "
                errmsg += "processed. This information was written to problem"
                errmsg += "_pipelines.yaml in " + self.cli.reportdir + "\n\n"
                self.cli.LOG.error(errmsg)

    def export_to_yaml(self, yaml_dict, job, reportdir):
        """ Write output files. """
        filename = 'triage_' + job + '.yml'
        file_path = os.path.join(reportdir, filename)
        if not os.path.isdir(reportdir):
            os.makedirs(reportdir)
        if not yaml_dict:
            yaml_dict['pipeline'] = {}
        with open(file_path, 'w') as outfile:
            outfile.write(yaml.safe_dump(yaml_dict, default_flow_style=False))
            self.cli.LOG.info(filename + " written to " + os.path.abspath(reportdir))


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
        self.LOG = utils.get_logger('doberman.analysis')
        self.cli()

    def cli(self):
        usage = "usage: %prog [options] pipeline_id1 pipeline_id2 ..."
        prsr = optparse.OptionParser(usage=usage)
        prsr.add_option('-b', '--usebuildnos', action='store_true',
                        dest='use_deploy', default=False,
                        help='use pipeline_deploy build numbers not pipelines')
        prsr.add_option('-c', '--config', action='store', dest='configfile',
                        default=None,
                        help='specify path to configuration file')
        prsr.add_option('-d', '--dburi', action='store', dest='database',
                        default=None,
                        help='set URI to bug/regex db: /path/to/mock_db.yaml')
        prsr.add_option('-J', '--jenkins', action='store', dest='jenkins_host',
                        default=None,
                        help='URL to Jenkins server')
        prsr.add_option('-k', '--keep', action='store_true', dest='keep_data',
                        default=False,
                        help='Do not delete extracted tarballs when finished')
        prsr.add_option('-v', '--verbose', action='store_true', dest='verbose',
                        default=False, help='Reduced text in output yaml.')
        prsr.add_option('-n', '--netloc', action='store', dest='netloc',
                        default=None,
                        help='Specify an IP to rewrite URLs')
        prsr.add_option('-o', '--output', action='store', dest='report_dir',
                        default=None,
                        help='specific the report output directory')
        prsr.add_option('-r', '--remote', action='store_true',
                        dest='run_remote', default=False,
                        help='set if running analysis remotely')
        prsr.add_option('-T', '--testcatalog', action='store', dest='tc_host',
                        default=None,
                        help='URL to test-catalog API server')
        prsr.add_option('-x', '--xmls', action='store', dest='xmls',
                        default=None,
                        help='XUnit files to parse as XML, not as plain text')
        (opts, args) = prsr.parse_args()

        # cli override of config values
        if opts.configfile:
            cfg = utils.get_config(opts.configfile)
        else:
            cfg = utils.get_config()

        self.database = opts.database
        self.LOG.info("database=%s" % self.database)
        # database filepath might be set in config
        if self.database is None:
            self.LOG.info('getting DB from config file')
            self.database = cfg.get('DEFAULT', 'database_uri')
            self.LOG.info('database=%s' % self.database)

        if opts.use_deploy:
            self.use_deploy = opts.use_deploy
        else:
            self.use_deploy = cfg.get('DEFAULT', 'use_deploy').lower() in \
                ['true', 'yes']

        if opts.jenkins_host:
            self.jenkins_host = opts.jenkins_host
        else:
            self.jenkins_host = cfg.get('DEFAULT', 'jenkins_url')

        if opts.verbose:
            self.reduced_output_text = False
        else:
            self.reduced_output_text = True

        # cli wins, then config, then hostname lookup
        netloc_cfg = cfg.get('DEFAULT', 'netloc')
        if opts.netloc:
            self.netloc = opts.netloc
        elif netloc_cfg not in ['None', 'none', None]:
            self.netloc = netloc_cfg
        else:
            self.netloc = \
                socket.gethostbyname(urlparse.urlsplit(opts.host).netloc)

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

        # Get arguments:
        self.ids = set(args)
        if not self.ids:
            raise Exception("No pipeline IDs provided")

if __name__ == "__main__":
    CrudeAnalysis()
    sys.exit()
