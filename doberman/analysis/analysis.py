#! /usr/bin/env python2

import sys
import os
import re
import yaml
import socket
import urlparse
import tarfile
import shutil
import uuid
import optparse
import datetime
import json
from test_catalog.client.api import TCClient
from test_catalog.client.base import TCCTestPipeline
from pandas import DataFrame
from lxml import etree
from jenkinsapi.jenkins import Jenkins as JenkinsAPI
from jenkinsapi.custom_exceptions import *
from doberman.common import pycookiecheat, utils

LOG = utils.get_logger('doberman.analysis')

# Special cases: A hard-coded dictionary linking the files that may be missing
# to a bug id on launchpad:
# TODO: Decide whether to keep this hard-coded or to use an external yaml, etc:
special_cases = {'juju_status.yaml': '1372407',
                 'oil_nodes': '1372411',
                 'pipeline_id': '1372567'}
job_names = ['pipeline_deploy', 'pipeline_prepare', 'test_tempest_smoke']


class Common(object):
    """ Common methods

    """

    def add_to_yaml(self, matching_bugs, build_status, link, existing_dict):
        """
        Creates a yaml dict and populates with data in the right format and 
        merges with existing yaml dict.

        """
        # Make dict
        pipeline_dict = {}
        yaml_dict = {}

        if matching_bugs != {}:
            pipeline_dict = {self.pipeline: {'status': build_status,
                                             'bugs': matching_bugs}}
            if hasattr(self, 'build_number'):
                pipeline_dict[self.pipeline]['build'] = self.build_number
            
            if link:
                pipeline_dict[self.pipeline]['link to jenkins'] = \
                    self.cli.jenkins_host + link
            pipeline_dict[self.pipeline]['link to test-catalog'] = \
                self.cli.tc_host.replace('api', "pipeline/" + self.pipeline)

        # Merge with existing dict:
        if existing_dict:
            if 'pipeline' in existing_dict:
                yaml_dict['pipeline'] = self.join_dicts(existing_dict['pipeline'],
                                                   pipeline_dict)
            else:
                yaml_dict['pipeline'] = self.join_dicts(existing_dict, pipeline_dict)
        else:
            yaml_dict['pipeline'] = pipeline_dict
        return yaml_dict
            
    def non_db_bug(self, bug_id, existing_dict, err_msg):
        """ Make non-database bugs for special cases, such as missing files that
            cannot be, or are not yet, listed in the bugs database.

        """
        matching_bugs = {}
        matching_bugs[bug_id] = {'regexps': err_msg, 'vendors': err_msg,
                                 'machines': err_msg, 'units': err_msg}
        yaml_dict = self.add_to_yaml(matching_bugs, 'FAILURE', None, existing_dict)
        return yaml_dict

    def join_dicts(self, old_dict, new_dict):
        """ Merge matching_bugs dictionaries. """
        earlier_items = list(old_dict.items())
        current_items = list(new_dict.items())
        return dict(earlier_items + current_items)



        
class CrudeAnalysis(Common):
    """ 
            
    """
    
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
            LOG.info(msg % ", ".join([str(i) for i in self.cli.ids]))
        self.calc_when_to_report()
        for pos, idn in enumerate(self.ids):
            if self.cli.use_deploy:
                pipeline = self.jenkins.get_pipeline_from_deploy_build(idn)
            else:
                pipeline = idn
            # Quickly cycle through to check all pipelines are real:
            if not self.jenkins.pipeline_check(pipeline):
                msg = "Pipeline ID \"%s\" is an unrecognised format" % pipeline
                LOG.error(msg)
                raise Exception(msg)
            self.pipeline_ids.append(pipeline)

            # Notify user/log of progress
            progress = [round((pc / 100.0) * len(self.ids))
                        for pc in self.report_at]
            if pos in progress:
                LOG.info("Pipeline lookup " + str(self.report_at[progress.index(pos)]) + "% complete.") 
        LOG.info("All pipelines checked. Now polling jenkins/ processing data")

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
            for folder in job_names:
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
                jenkins = self.jenkins
                bugs = self.test_catalog.bugs
                deploy = Deploy(deploy_build, 'pipeline_deploy', jenkins,
                                deploy_yaml_dict, self.cli, bugs, pipeline_id)
                deploy_yaml_dict = deploy.yaml_dict
                
                if prepare_build and not deploy.still_running:
                    prepare = Prepare(prepare_build, 'pipeline_prepare', 
                                      jenkins, prepare_yaml_dict, self.cli, bugs,
                                      pipeline_id, deploy)
                    prepare_yaml_dict = prepare.yaml_dict
                
                if tempest_build and not deploy.still_running:
                    tempest = Tempest(tempest_build, 'test_tempest_smoke',
                                      jenkins, tempest_yaml_dict, self.cli, bugs,
                                      pipeline_id, prepare)
                    tempest_yaml_dict = tempest.yaml_dict
            
                if deploy.still_running:
                    LOG.error("%s is still running - skipping" % deploy_build)
            except:
                if 'deploy_build' not in locals():
                    msg = "Cannot acquire pipeline deploy build number"
                    msg += " (may be cookie related?)"
                    deploy_yaml_dict = \
                        self.non_db_bug(special_cases['pipeline_id'],
                                        deploy_yaml_dict, msg)
                else:
                    print("Problem with " + pipeline_id + " - skipping (deploy_build:"
                          + " " + deploy_build + ")")
                    problem_pipelines.append((pipeline_id, deploy_build))

        # Export to yaml:
        self.export_to_yaml(deploy_yaml_dict, 'pipeline_deploy', self.cli.reportdir)
        self.export_to_yaml(prepare_yaml_dict, 'pipeline_prepare', self.cli.reportdir)
        self.export_to_yaml(tempest_yaml_dict, 'test_tempest_smoke', self.cli.reportdir)
        
        # Write to file any pipelines (plus deploy build) that failed processing:
        if not problem_pipelines == []:
            file_path = os.path.join(self.cli.reportdir, 'problem_pipelines.yaml')
            open(file_path, 'a').close()  # Create file if doesn't exist yet
            with open(file_path, 'r+') as pp_file:
                existing_content = pp_file.read()
                pp_file.seek(0, 0)  # Put at beginning of file
                pp_file.write("\n" + str(datetime.datetime.now())
                              + "\n--------------------------\n")
                for problem_pipeline in problem_pipelines:
                    pp_file.write("%s (deploy build: %s) \n" % problem_pipeline)
                pp_file.write(existing_content)
                errmsg = "There were some pipelines that could not be processed. "
                errmsg += "This information was written to problem_pipelines.yaml "
                errmsg += "in " + self.cli.reportdir + "\n\n"
                LOG.error(errmsg)
    
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
            LOG.info(filename + " written to " + os.path.abspath(reportdir))


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
        prsr.add_option('-l', '--less', action='store_true', dest='less',
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
        LOG.info("database=%s" % self.database)
        # database filepath might be set in config
        if self.database is None:
            LOG.info('getting DB from config file')
            self.database = cfg.get('DEFAULT', 'database_uri')
            LOG.info('database=%s' % self.database)

        if opts.use_deploy:
            self.use_deploy = opts.use_deploy
        else:
            self.use_deploy = cfg.get('DEFAULT', 'use_deploy').lower() in \
                ['true', 'yes']

        if opts.jenkins_host:
            self.jenkins_host = opts.jenkins_host
        else:
            self.jenkins_host = cfg.get('DEFAULT', 'jenkins_url')

        if opts.less:
            self.reduced_output_text = True
        else:
            self.reduced_output_text = False

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
            LOG.error("Missing jenkins configuration")
            raise Exception("Missing jenkins configuration")

        if self.tc_host in [None, 'None', 'none', '']:
            LOG.error("Missing test-catalog configuration")
            raise Exception("Missing test-catalog configuration")

        # Cookie for test-catalog:
        tc_auth = cfg.get('DEFAULT', 'tc_auth')
        try:
            self.tc_auth = json.load(open(tc_auth))
        except:
            msg = "Cannot find cookie for test-catalog: %s" % tc_auth
            LOG.error(msg)
            raise Exception(msg)
        LOG.debug('tc_auth token=%s' % self.tc_auth)

        # Get arguments:
        self.ids = set(args)
        if not self.ids:
            raise Exception("No pipeline IDs provided")
        
class Jenkins(Common):
    """            
    """
    
    def __init__(self, cli):
        self._jenkins = []
        self.cli = cli
        self.netloc = self.cli.netloc
        self.cookie = None  # TODO: Set this somewhere!!!
        self.connect_to_jenkins()
        try:
            self._jenkins.append(self.jenkins_api)
        except:
            msg = "Problem connecting to Jenkins (try refreshing cookies?)"
            LOG.error(msg)
            raise Exception(msg)
        
    def connect_to_jenkins(self):
        """ Connects to jenkins via jenkinsapi, returns a jenkins object. """

        url = self.cli.jenkins_host
        remote = self.cli.run_remote
        LOG.debug('Connecting to jenkins @ %s remote=%s' % (url, remote))

        if remote:
            LOG.info("Fetching cookies for %s" % url)
            self.cookie = pycookiecheat.chrome_cookies(url)
        try:
            self.jenkins_api = JenkinsAPI(baseurl=url, cookies=self.cookie,
                                          netloc=self.netloc)
        except JenkinsAPIException:
            LOG.exception('Failed to connect to Jenkins')

    def get_pipeline_from_deploy_build(self, id_number):
        deploy_bld_n = int(id_number)
        try:
            deploy = self.jenkins_api['pipeline_deploy']
            cons = deploy.get_build(deploy_bld_n).get_console()
        except:
            msg = "Failed to fetch pipeline from deploy build: \"%s\" - if "
            msg += "this is already a pipeline id, run without the '-b' flag."
            raise Exception(msg % deploy_bld_n)
        pl_plus_fluff = cons.split('pipeline_id')[1].split('|\n')[0]
        pl = pl_plus_fluff.replace('|', '').strip()
        if self.pipeline_check(pl):
            return pl
        else:
            pl = cons.split('PIPELINE_ID=')[1].replace('\n++ ', '')
            if self.pipeline_check(pl):
                return pl
            else:
                msg = "Pipeline ID \"%s\" is an unrecognised format" % pl
                LOG.error(msg)
                raise Exception(msg)

    def pipeline_check(self, pipeline_id):
        return [8, 4, 4, 4, 12] == [len(x) for x in pipeline_id.split('-')] 

    def get_triage_data(self, build_num, job, reportdir):
        """ Get the artifacts from jenkins via jenkinsapi object. """
        jenkins_job = self.jenkins_api[job]
        build = jenkins_job.get_build(int(build_num))
        outdir = os.path.join(self.cli.reportdir, job, str(build_num))
        LOG.info('Downloading debug data to: %s' % (outdir))
        # Check to make sure it is not still running!:
        if build._data['duration'] == 0:
            return True  # Still running
        try:
            os.makedirs(outdir)
        except OSError:
            if not os.path.isdir(outdir):
                raise
        with open(os.path.join(outdir, "console.txt"), "w") as cnsl:
            LOG.info('Saving console @ %s to %s' % (build.baseurl, outdir))
            console = build.get_console()
            cnsl.write(console)
            cnsl.write('\n')
            cnsl.flush()

        for artifact in build.get_artifacts():
            artifact.save_to_dir(outdir)
            self.extract_and_delete_archive(outdir, artifact)
        return False  # Not still running
 
    def extract_and_delete_archive(self, outdir, artifact):
        """ Extracts the contents of a tarball and places it into a new file
            of the samename without the .tar.gz suffix (N.B. this leaves
            .ring.gz intact as they seem to contain binary ring files that
            I'm not sure what to do with at this point).

        """
        try:
            if 'tar.gz' in artifact.filename:
                path_to_artifact = os.path.join(outdir, artifact.filename)
                with tarfile.open(path_to_artifact, 'r:gz') as tar:
                    tarlist = \
                        [member for member in tar.getmembers() if member.isfile()]
                    for compressed_file in tarlist:
                        slug = compressed_file.name.replace('/', '_')
                        with open(os.path.join(outdir, slug), 'w') as new_file:
                            data = tar.extractfile(compressed_file).readlines()
                            new_file.writelines(data)
                os.remove(os.path.join(outdir, artifact.filename))
        except:
            LOG.error("Could not extract %s" % artifact.filename)
            
class TestCatalog(Common):
    """            
    """
    
    def __init__(self, cli):
        
        self.cli = cli
        self.cookie = self.cli.tc_auth
        self.tc_client = TCClient
        self._tc_client = []
        self.get_tc_client()
        self.open_bug_database()  # Connect to bugs DB

    def open_bug_database(self):
        if self.cli.database in [None, 'None', 'none', '']:
            LOG.info("Connecting to test-catalog bug/regex database")
            self.b = self.client.get_bug_info(force_refresh=True)            
        elif len(self.cli.database):
            LOG.info("Connecting to database file: %s" % (self.cli.database))
            with open(self.cli.database, "r") as mock_db_file:
                self.bugs = yaml.load(mock_db_file)['bugs']
        else:
            LOG.error('Unknown database: %s' % (self.cli.database))
            raise Exception('Invalid Database configuration')

    def get_tc_client(self):
        if self._tc_client and not self.cli.tc_host:
            self.client = self._tc_client[0]
        self.connect_to_testcatalog()
        self._tc_client.append(self.client)
    
    def connect_to_testcatalog(self):
        LOG.debug('Connecting to test-catalog @ %s remote=%s'
                  % (self.cli.tc_host, self.cli.run_remote))
        if self.cookie is None:
            LOG.info("Fetching test-catalog cookies for %s" % self.cli.tc_host)
            self.cookie = pycookiecheat.chrome_cookies(self.cli.tc_host)
        LOG.info("Fetching test-catalog using endpoint=%s" % self.cli.tc_host)
        self.client = self.tc_client(endpoint=self.cli.tc_host,
                                     cookies=self.cookie)

    def get_pipelines(self, pipeline):
        """ Using test-catalog, return the build numbers for the jobs that are
            part of the given pipeline.

        """
        LOG.info('Fetching data on pipeline: %s' % (pipeline))        
        try:
            pl_tcat = TCCTestPipeline(self.client, pipeline)
        except Exception, e:
            msg = "test-catalog error. Does pipeline exist? Is there a cookie-"
            msg += "related issue? (%s)" % e
            LOG.error(msg)
            raise Exception(msg)
        try:
            deploy_dict = pl_tcat.dict['parent']
            deploy_build = deploy_dict['build_tag'].split("-")[-1]
        except:
            deploy_build = None
        try:
            prepare_dict = deploy_dict['children'][0]
            prepare_build = prepare_dict['build_tag'].split("-")[-1]
        except:
            prepare_build = None
        try:
            tempest_dict = prepare_dict['children'][0]
            tempest_build = tempest_dict['build_tag'].split("-")[-1]
        except:
            tempest_build = None

        return (deploy_build, prepare_build, tempest_build)
        
    def pipeline_check(self, pipeline_id):
        return [8, 4, 4, 4, 12] == [len(x) for x in pipeline_id.split('-')] 
            
class Build(Common):
    """            
    """
    
    def __init__(self, build_number, jobname, jenkins, yaml_dict, cli, bugs,
                 pipeline):
        # Pull console and artifacts from jenkins:
        self.still_running = jenkins.get_triage_data(build_number, jobname,
                                                     cli.reportdir)
        self.build_number = build_number
        self.jobname = jobname
        self.jenkins = jenkins
        self.yaml_dict = yaml_dict
        self.cli = cli
        self.bugs = bugs
        self.pipeline = pipeline
        
    def get_yaml(self, file_location, yaml_dict):
        try:
            with open(file_location, "r") as f:
                return (yaml.load(f), yaml_dict)
        except IOError, e:
            file_name = file_location.split('/')[-1]
            LOG.error("%s: %s is not in artifacts folder (%s)"
                      % (self.pipeline, file_name, e[1]))
            msg = file_name + ' MISSING'
            yaml_dict = self.non_db_bug(special_cases[file_name], yaml_dict, msg)
            return (None, yaml_dict)

    def bug_hunt(self, oil_df, path):
        """ Using information from the bugs database, opens target file and
            searches the text for each associated regexp. """
        # TODO: As it stands, files are only searched if there is an entry in the
        # DB. This shouldn't be a problem if there is always a dummy bug in the DB
        # for the important files such as console and tempest_xunit.xml FOR EACH
        # JOB TYPE (i.e. pipeline_deploy, pipeline_prepare and test_tempest_smoke).        
        parse_as_xml = self.cli.xmls
        build_status = [build_info for build_info in self.jenkins.jenkins_api[self.jobname]._poll()['builds']
                        if build_info['number'] == int(self.build_number)][0]['result']
        matching_bugs = {}
        units_list = oil_df['service'].tolist()
        machines_list = oil_df['node'].tolist()
        vendors_list = oil_df['vendor'].tolist()
        charms_list = oil_df['charm'].tolist()
        ports_list = oil_df['ports'].tolist()
        states_list = oil_df['state'].tolist()
        slaves_list = oil_df['slaves'].tolist()
        
        bug_unmatched = True
        info = {}
        if not self.bugs:
            raise Exception("No bugs in database!")
        for bug_id in self.bugs.keys():
            if self.jobname in self.bugs[bug_id]:
                # Any of the dicts in self.bugs[bug_id][self.jobname] can match (or):
                or_dict = self.bugs[bug_id][self.jobname]
                for and_dict in or_dict:
                    # Within the dictionary all have to match (and):
                    hit_dict = {}
                    # Load up the file for each target_file in the DB for this bug:
                    for target_file in and_dict.keys():
                        target_location = os.path.join(path, target_file)
                        try:
                            for bssub in self.bsnode:
                                if 'bootstrap_node' not in info:
                                    info['bootstrap_node'] = {}
                                info['bootstrap_node'][bssub] = self.bsnode[bssub]
                        except:
                            pass
                        if not os.path.isfile(target_location):
                            info['error'] = target_file + " not present"
                            break                        
                        if target_file == 'console.txt':
                            link2 = '/job/%s/%s/console' % (self.jobname, self.build_number)
                        else:
                            link2 = ('/job/%s/%s/artifact/artifacts/%s'
                                     % (self.jobname, self.build_number, target_file))
                        if not (target_file in parse_as_xml):
                            with open(target_location, 'r') as grep_me:
                                text = grep_me.read()
                            hit = self.rematch(and_dict, target_file, text)
                            if hit:
                                hit_dict = self.join_dicts(hit_dict, hit)
                            else:
                                info['target file'] = target_file
                                if not self.cli.reduced_output_text:
                                    info['text'] = text
                        else:
                            # Get tempest results:
                            p = etree.XMLParser(huge_tree=True)
                            doc = etree.parse(target_location, parser=p).getroot()
                            errors_and_fails = doc.xpath('.//failure')
                            errors_and_fails += doc.xpath('.//error')
                            # TODO: There is not currently a way to do multiple
                            # 'and' regexps within a single tempest file - you can
                            # do console AND tempest or tempest OR tempest, but not
                            # tempest AND tempest. Needs it please!
                            for num, fail in enumerate(errors_and_fails):
                                pre_log = fail.get('message')\
                                    .split("begin captured logging")[0]
                                hit = self.rematch(and_dict, target_file, pre_log)
                                if hit:
                                    hit_dict = self.join_dicts(hit_dict, hit)
                                else:
                                    info['target file'] = target_file
                                    if not self.cli.reduced_output_text:
                                        info['text'] = pre_log
                                info['xunit class'] = \
                                    fail.getparent().get('classname')
                                info['xunit name'] = fail.getparent().get('name')

                    if and_dict == hit_dict:
                        matching_bugs[bug_id] = {'regexps': hit_dict,
                                                 'vendors': vendors_list,
                                                 'machines': machines_list,
                                                 'units': units_list,
                                                 'charms': charms_list,
                                                 'ports': ports_list,
                                                 'states': states_list,
                                                 'slaves': slaves_list}
                        if info:
                            matching_bugs[bug_id]['additional info'] = info
                        LOG.info("Bug found!")
                        LOG.info(hit_dict)
                        hit_dict = {}
                        bug_unmatched = False
                        break
        if bug_unmatched and build_status == 'FAILURE':
            bug_id = 'unfiled-' + str(uuid.uuid4())
            matching_bugs[bug_id] = {'regexps': 'NO REGEX - UNFILED/UNMATCHED BUG',
                                     'vendors': vendors_list,
                                     'machines': machines_list,
                                     'units': units_list,
                                     'charms': charms_list,
                                     'ports': ports_list,
                                     'states': states_list,
                                     'slaves': slaves_list}                                     
            LOG.info("Unfiled bug found!")
            hit_dict = {}
            if info:
                matching_bugs[bug_id]['additional info'] = info
        return (matching_bugs, build_status, link2)


    def rematch(self, bugs, target_file, text):
        """ Search files in bugs for multiple matching regexps. """
        regexps = bugs[target_file]['regexp']

        if type(regexps) == list:
            if len(regexps) > 1:
                regexp = '|'.join(regexps)
            else:
                regexp = regexps[0]
            set_re = set(regexps)
        else:
            regexp = regexps
            set_re = set([regexps])
        if regexp not in ['None', None, '']:
            matches = re.compile(regexp, re.DOTALL).findall(text)
            # TODO: This checks that they match, but not that they do so in the
            # correct order yet:
            if matches:
                if len(set_re) == len(set(matches)):
                    return {target_file: {'regexp': regexps}}
        
class Deploy(Build):
    """            
    """
    
    def __init__(self, build_number, jobname, jenkins, yaml_dict, cli, bugs,
                 pipeline):
        super(Deploy, self).__init__(build_number, jobname, jenkins, yaml_dict,
                                     cli, bugs, pipeline)
        # Process downloaded data:
        self.process_deploy_data()

    def process_deploy_data(self):
        """ Parses the artifacts files from a single pipeline into data and
            metadata DataFrames

        """
        reportdir = self.cli.reportdir
        deploy_build = self.build_number
        pline = self.pipeline
        pipeline_deploy_path = os.path.join(reportdir, self.jobname,
                                            deploy_build)
        self.oil_df = DataFrame(columns=('node', 'service', 'vendor', 'charm',
                                         'ports', 'state', 'slaves'))

        # Read oil nodes file:
        oil_node_location = os.path.join(pipeline_deploy_path, 'oil_nodes')
        oil_nodes_yml, self.yaml_dict = self.get_yaml(oil_node_location,
                                                      self.yaml_dict)
        if not oil_nodes_yml:
            return
        else:
            oil_nodes = DataFrame(oil_nodes_yml['oil_nodes'])
            oil_nodes.rename(columns={'host': 'node'}, inplace=True)

        # Read juju status file:
        juju_status_location = os.path.join(pipeline_deploy_path,
                                            'juju_status.yaml')
        juju_status, self.yaml_dict = self.get_yaml(juju_status_location,
                                                    self.yaml_dict)
        if not juju_status:
            return

        # Get info for bootstrap node (machine 0):
        machine_info = juju_status['machines']['0']
        m_name = machine_info['dns-name']
        m_os = machine_info['series']
        machine = m_os + " running " + m_name
        state = machine_info['agent-state']
        self.bsnode = {'machine': machine, 'state': state}

        row = 0
        for service in juju_status['services']:
            serv = juju_status['services'][service]
            charm = serv['charm'] if 'charm' in serv else 'Unknown'
            if 'units' in serv:
                units = serv['units']
            else:
                units = {}
                self.oil_df.loc[row] = ['N/A', 'N/A', 'N/A', charm, 'N/A',
                                        'N/A', 'N/A']
                
            for unit in units:
                this_unit = units[unit]
                ports = ", ".join(this_unit['open-ports']) if 'open-ports' \
                    in this_unit else "N/A"
                machine_no = this_unit['machine'].split('/')[0]
                machine_info = juju_status['machines'][machine_no]
                if 'hardware' in machine_info:
                    hardware = [hw.split('hardware-')[1] for hw in \
                                machine_info['hardware'].split('tags=')\
                                [1].split(',') if 'hardware-' in hw]
                    slave = ", ".join([str(slv) for slv in \
                                machine_info['hardware'].split('tags=')[1]\
                                .split(',') if 'slave' in slv])
                else:
                    hardware = ['Unknown']
                    slave = 'Unknown'                            
                if '/' in this_unit['machine']:
                    container_name = this_unit['machine']
                    container = machine_info['containers'][container_name]
                elif 'containers' in machine_info:
                    if len(machine_info['containers'].keys()) == 1:
                        container_name = machine_info['containers'].keys()[0]
                        container = machine_info['containers'][container_name]
                    else:
                        container = []  # TODO: Need to find a way to identify
                                        # which container is being used here
                else:
                    container = []
                
                m_name = machine_info['dns-name']
                state = machine_info['agent-state'] + ". "
                state += container['agent-state-info'] + ". " \
                    if 'agent-state-info' in container else ''
                state += container['instance-id'] if 'instance-id' in \
                    container else ''
                m_ip = " (" + container['dns-name'] + ")" \
                       if 'dns-name' in container else ""
                machine = m_name + m_ip
                self.oil_df.loc[row] = [machine, unit, ', '.join(hardware),
                                        charm, ports, state, slave]
                row += 1
            
        matching_bugs, build_status, link = self.bug_hunt(self.oil_df,
                                                          pipeline_deploy_path)
        self.yaml_dict = self.add_to_yaml(matching_bugs, build_status, link,
                                          self.yaml_dict)
    

class Prepare(Build):
    """            
    """
    
    def __init__(self, build_number, jobname, jenkins, yaml_dict, cli, bugs,
                 pipeline, deploy):
        super(Prepare, self).__init__(build_number, jobname, jenkins,
                                      yaml_dict, cli, bugs, pipeline)
        self.oil_df = deploy.oil_df
        self.yaml_dict = deploy.yaml_dict
        
        # Process downloaded data:
        self.process_prepare_data()

    def process_prepare_data(self):
        """ Parses the artifacts files from a single pipeline into data and
            metadata DataFrames.

        """
        prepare_path = os.path.join(self.cli.reportdir, 'pipeline_prepare',
                                    self.build_number)
        matching_bugs, build_status, link = self.bug_hunt(self.oil_df,
                                                          prepare_path)
        self.yaml_dict = self.add_to_yaml(matching_bugs, build_status, link,
                                          self.yaml_dict)


class Tempest(Build):
    """
    """

    def __init__(self, build_number, jobname, jenkins, yaml_dict, cli, bugs,
                 pipeline, prepare):
        super(Tempest, self).__init__(build_number, jobname, jenkins,
                                      yaml_dict, cli, bugs, pipeline)
        self.oil_df = prepare.oil_df
        self.yaml_dict = prepare.yaml_dict

        # Process downloaded data:
        self.process_tempest_data()

    def process_tempest_data(self):
        """
        Parses the artifacts files from a single pipeline into data and
        metadata DataFrames

        """
        tts_path = os.path.join(self.cli.reportdir, 'test_tempest_smoke',
                                self.build_number)
        matching_bugs, build_status, link = \
            self.bug_hunt(self.oil_df, tts_path)
        self.yaml_dict = self.add_to_yaml(matching_bugs, build_status, link,
                                          self.yaml_dict)

if __name__ == "__main__":
    CrudeAnalysis()
    sys.exit()
