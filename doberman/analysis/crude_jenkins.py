
import os
import re
import tarfile
import uuid
import bisect
import time
from lxml import etree
from jenkinsapi.jenkins import Jenkins as JenkinsAPI
from doberman.common import pycookiecheat
from doberman.common.common import Common
from jenkinsapi.custom_exceptions import *
from glob import glob
from file_parser import FileParser


class Jenkins(Common):
    """
    """

    def __init__(self, cli):
        self._jenkins = []
        self.cli = cli
        self.netloc = self.cli.netloc
        self.cookie = None
        self.connect_to_jenkins()
        try:
            self._jenkins.append(self.jenkins_api)
        except:
            msg = "Problem connecting to Jenkins (try refreshing cookies?)"
            self.cli.LOG.error(msg)
            raise Exception(msg)

    def connect_to_jenkins(self):
        """ Connects to jenkins via jenkinsapi, returns a jenkins object. """

        url = self.cli.jenkins_host
        remote = self.cli.run_remote
        self.cli.LOG.debug('Connecting to jenkins @ {0} remote={1}'.format(url,
                           remote))

        if remote:
            self.cli.LOG.info("Fetching cookies for %s" % url)
            self.cookie = pycookiecheat.chrome_cookies(url)
        try:
            self.jenkins_api = JenkinsAPI(baseurl=url, cookies=self.cookie,
                                          netloc=self.netloc)
        except JenkinsAPIException:
            self.cli.LOG.exception('Failed to connect to Jenkins')

    def get_pipeline_from_deploy_build(self, id_number):
        deploy_bld_n = int(id_number)
        try:
            deploy = self.jenkins_api['pipeline_deploy']
            cons = deploy.get_build(deploy_bld_n).get_console()
        except:
            if self.cli.use_deploy:
                msg = "'{0}' is an unrecognised pipeline_deploy build number"
            else:
                msg = "Failed to fetch pipeline from deploy build: \"{0}\" - "
                msg += "if this is already a pipeline id, run without the '-b'"
                msg += " flag."
            self.cli.LOG.exception(msg.format(deploy_bld_n))
            return
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
                self.cli.LOG.error(msg)
                raise Exception(msg)

    def pipeline_check(self, pipeline_id):
        try:
            return [8, 4, 4, 4, 12] == [len(x) for x in pipeline_id.split('-')]
        except:
            return False

    def write_console_to_file(self, build, outdir):
        with open(os.path.join(outdir, "console.txt"), "w") as cnsl:
            self.cli.LOG.debug('Saving console @ {0} to {1}'.format(
                               build.baseurl, outdir))
            console = build.get_console()
            cnsl.write(console)
            cnsl.write('\n')
            cnsl.flush()

    def find_build_newer_than(self, builds, start):
        """
        assumes builds has been sorted
        """

        # pre calculate key list
        keys = [r['timestamp'] for r in builds]

        # make a micro timestamp from input
        start_ts = int(time.mktime(start.timetuple())) * 1000

        # find leftmost item greater than or equal to start
        i = bisect.bisect_left(keys, start_ts)
        if i != len(keys):
            return i

        self.cli.LOG.error("No job newer than %s" % (start))
        return None

    def get_triage_data(self, build_num, job, reportdir, console_only=False):
        """ Get the artifacts from jenkins via jenkinsapi object. """
        jenkins_job = self.jenkins_api[job]
        build = jenkins_job.get_build(int(build_num))
        outdir = os.path.join(self.cli.reportdir, job, str(build_num))

        # Check to make sure it is not still running!:
        if build._data['duration'] == 0:
            return True  # Still running
        try:
            os.makedirs(outdir)
        except OSError:
            if not os.path.isdir(outdir):
                raise
        self.write_console_to_file(build, outdir)

        if not console_only:
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
                    tarlist = [member for member in tar.getmembers()
                               if member.isfile()]
                    for compressed_file in tarlist:
                        slug = compressed_file.name.replace('/', '_')
                        with open(os.path.join(outdir, slug), 'w') as new_file:
                            data = tar.extractfile(compressed_file).readlines()
                            new_file.writelines(data)
                os.remove(os.path.join(outdir, artifact.filename))
        except:
            self.cli.LOG.error("Could not extract %s" % artifact.filename)


class Build(Common):
    """
    """

    def __init__(self, build_number, jobname, jenkins, yaml_dict, cli, bugs,
                 pipeline):
        self.cli = cli
        self.fetch_data_if_appropriate(jenkins, jobname, build_number)
        self.build_number = build_number
        self.jobname = jobname
        self.jenkins = jenkins
        self.yaml_dict = yaml_dict
        self.bugs = bugs
        self.pipeline = pipeline

    def fetch_data_if_appropriate(self, jenkins, jobname, build_number):
        """ Pull console and artifacts from jenkins """
        path = os.path.join(self.cli.reportdir, jobname, build_number)
        if self.cli.dont_replace:
            if not os.path.exists(path):
                self.cli.LOG.info("{} missing - redownloading data"
                                  .format(path))
                self.still_running = (jenkins.get_triage_data(build_number,
                                      jobname, self.cli.reportdir))
            else:
                self.still_running = False
        else:
            self.still_running = jenkins.\
                get_triage_data(build_number, jobname, self.cli.reportdir)

    def bug_hunt(self, path, announce=True):
        """ Using information from the bugs database, opens target file and
            searches the text for each associated regexp. """
        # TODO: As it stands, files are only searched if there is an entry in
        # the DB. This shouldn't be a problem if there is always a dummy bug in
        # the DB for the important files such as console and tempest_xunit.xml
        # FOR EACH JOB TYPE (i.e. pipeline_deploy, pipeline_prepare and
        # test_tempest_smoke).

        parse_as_xml = self.cli.xmls
        xml_files_parsed = []
        # TODO: This still polls jenkins, even in 'offline' mode:
        build_details = [build_info for build_info in self.jenkins.jenkins_api
                         [self.jobname]._poll()['builds'] if build_info
                         ['number'] == int(self.build_number)][0]
        build_status = (build_details['result'] if 'result' in build_details
                        else 'Unknown')
        matching_bugs = {}

        bug_unmatched = True
        if not self.bugs:
            raise Exception("No bugs in database!")

        unfiled_xml_fails = {}
        for bug_id in self.bugs.keys():
            if self.jobname in self.bugs[bug_id]:
                # Any dict in self.bugs[bug_id][self.jobname] can match (or):
                or_dict = self.bugs[bug_id][self.jobname]
                for and_dict in or_dict:
                    # Within the dictionary all have to match (and):
                    hit_dict = {}
                    glob_hits = []
                    # Load up file for each target_file in the DB for this bug:
                    for target_file in and_dict.keys():
                        info = {}
                        try:
                            for bssub in self.bsnode:
                                if 'bootstrap_node' not in info:
                                    info['bootstrap_node'] = {}
                                info['bootstrap_node'][bssub] =\
                                    self.bsnode[bssub]
                        except:
                            pass
                        globs = glob(os.path.join(path, target_file))
                        if len(globs) == 0:
                            info['error'] = target_file + " not present"
                            break
                        for target_location in globs:
                            try:
                                target = target_location.split(os.sep)[-1]
                            except:
                                target = target_file
                            if not (target in parse_as_xml):
                                with open(target_location, 'r') as grep_me:
                                    text = grep_me.read()
                                hit = self.rematch(and_dict, target, text)
                                if hit:
                                    glob_hits.append(
                                        target_location.split('/')[-1])
                                    hit_dict = self.join_dicts(hit_dict, hit)
                                    self.message = 0
                                else:
                                    info['target file'] = target
                                    if not self.cli.reduced_output_text:
                                        info['text'] = text
                            else:
                                if target in xml_files_parsed:
                                    xml_unparsed = False
                                else:
                                    xml_unparsed = True
                                    xml_files_parsed.append(target)
                                # Get tempest results:
                                p = etree.XMLParser(huge_tree=True)
                                et = etree.parse(target_location, parser=p)
                                doc = et.getroot()
                                errors_and_fails = doc.xpath('.//failure')
                                errors_and_fails += doc.xpath('.//error')
                                # TODO: There is not currently a way to do
                                # multiple 'and' regexps within a single
                                # tempest file - you can do console AND tempest
                                # or tempest OR tempest, but not tempest AND
                                # tempest. Needs it please!
                                if xml_unparsed:
                                    unfiled_xml_fails = self.populate_uxfs(
                                        errors_and_fails, info, target,
                                        bug_unmatched, build_status,
                                        unfiled_xml_fails)
                                for num, fail in enumerate(errors_and_fails):
                                    pre_log = fail.get('message')
                                    if not self.cli.reduced_output_text:
                                            info['text'] = pre_log
                                    info['target file'] = target
                                    info['xunit class'] = \
                                        fail.getparent().get('classname')
                                    info['xunit name'] = \
                                        fail.getparent().get('name')
                                    hit = self.rematch(and_dict, target,
                                                       pre_log)
                                    if hit:
                                        # Add to hit_dict:
                                        hit_dict = self.join_dicts(hit_dict,
                                                                   hit)
                                        # Remove hit from unfiled_xml_fails:
                                        edited_uxfs = unfiled_xml_fails.copy()

                                        for uxf in unfiled_xml_fails:
                                            removeme = edited_uxfs[uxf]
                                            addinfo = removeme.get(
                                                'additional info')
                                            xname = addinfo['xunit name']
                                            namecheck = \
                                                (xname == info['xunit name'])
                                            xclass = addinfo['xunit class']
                                            classcheck = \
                                                (xclass == info['xunit class'])
                                            if (namecheck and classcheck):
                                                del edited_uxfs[uxf]
                                        unfiled_xml_fails = edited_uxfs.copy()
                                # TODO: But if there are multiple globs, it'll
                                # overwrite these in the xml - FIXME!!!

                    if and_dict == hit_dict:
                        links = []
                        url = self.cli.external_jenkins_url
                        if (not glob_hits) and (target_file in parse_as_xml):
                            glob_hits = [target_file]
                        for hit_file in glob_hits:
                            if hit_file == "console.txt":
                                link = '{0}/job/{1}/{2}/console'
                                links.append(link.format(url, self.jobname,
                                             self.build_number))
                            else:
                                link = '{0}/job/{1}/{2}/artifact/artifacts/{3}'
                                links.append(link.format(url, self.jobname,
                                             self.build_number, hit_file))
                        jlink = ", ".join(links)
                        matching_bugs[bug_id] = \
                            {'regexps': hit_dict,
                             'vendors': self.oil_df['vendor'],
                             'machines': self.oil_df['node'],
                             'units': self.oil_df['service'],
                             'charms': self.oil_df['charm'],
                             'ports': self.oil_df['ports'],
                             'states': self.oil_df['state'],
                             'slaves': self.oil_df['slaves'],
                             'link to jenkins': jlink, }
                        if info:
                            matching_bugs[bug_id]['additional info'] = info
                        self.cli.LOG.info("Bug found! ({0}, bug #{1})"
                                          .format(self.jobname, bug_id))
                        self.cli.LOG.info(hit_dict)
                        hit_dict = {}
                        bug_unmatched = False
                        break
        matching_bugs = self.join_dicts(matching_bugs, unfiled_xml_fails)

        if bug_unmatched and (build_status == 'FAILURE' or
                              build_status == 'Unknown'):
            bug_id = 'unfiled-' + str(uuid.uuid4())
            jlink = (self.cli.external_jenkins_url + '/job/{0}/{1}/console'
                     .format(self.jobname, self.build_number))
            matching_bugs[bug_id] = {'regexps':
                                     'NO REGEX - UNFILED/UNMATCHED BUG',
                                     'vendors': self.oil_df['vendor'],
                                     'machines': self.oil_df['node'],
                                     'units': self.oil_df['service'],
                                     'charms': self.oil_df['charm'],
                                     'ports': self.oil_df['ports'],
                                     'states': self.oil_df['state'],
                                     'slaves': self.oil_df['slaves'],
                                     'link to jenkins': jlink, }
            if announce:
                self.cli.LOG.info("Unfiled bug found! ({0})"
                                  .format(self.jobname))
            self.message = 1
            matching_bugs[bug_id]['additional info'] = info
        else:
            if self.message != 1:
                self.message = 0
        return (matching_bugs, build_status)

    def populate_uxfs(self, errors_and_fails, info, target, bug_unmatched,
                      build_status, unfiled_xml_fails):
        """ Populates unfiled_xml_fails dictionary. """
        uxf_dict = {}
        for fail in errors_and_fails:
            specific_info = info.copy()
            pre_log = fail.get('message').split("begin captured logging")[0]
            if not self.cli.reduced_output_text:
                specific_info['text'] = pre_log
            specific_info['target file'] = target
            specific_info['xunit class'] = fail.getparent().get('classname')
            specific_info['xunit name'] = fail.getparent().get('name')

            bug_id = 'unfiled-' + str(uuid.uuid4())
            jlink = ('{0}/job/{1}/{2}/console'
                     .format(self.cli.external_jenkins_url, self.jobname,
                             self.build_number))
            uxf_dict[bug_id] = {'regexps': 'NO REGEX - UNFILED/UNMATCHED BUG',
                                'vendors': self.oil_df['vendor'],
                                'machines': self.oil_df['node'],
                                'units': self.oil_df['service'],
                                'charms': self.oil_df['charm'],
                                'ports': self.oil_df['ports'],
                                'states': self.oil_df['state'],
                                'slaves': self.oil_df['slaves'],
                                'link to jenkins': jlink, }
            uxf_dict[bug_id]['additional info'] = specific_info

        return uxf_dict

    def rematch(self, bugs, target_file, text):
        """ Search files in bugs for multiple matching regexps. """
        target_bugs = bugs.get(target_file, bugs.get('*'))
        regexps = target_bugs.get('regexp')

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
        self.message = 1

        # Process downloaded data:
        self.process_deploy_data()

    def process_deploy_data(self):
        """ Parses the artifacts files from a single pipeline into data and
            metadata

        """
        reportdir = self.cli.reportdir
        deploy_build = self.build_number
        self.bsnode = {}
        pipeline_deploy_path = os.path.join(reportdir, self.jobname,
                                            deploy_build)
        self.oil_df = {}
        self.oil_nodes = {}

        # Parse console:
        console_parser = FileParser(pipeline_deploy_path, 'console.txt')
        for err in console_parser.status:
            self.cli.LOG.error(err)
        self.bsnode = console_parser.bsnode
        
        # Parse oil_nodes:
        oil_nodes_parser = FileParser(pipeline_deploy_path, 'oil_nodes')
        for err in oil_nodes_parser.status:
            self.cli.LOG.error(err)
        self.oil_nodes = oil_nodes_parser.oil_nodes

        # Parse juju_status:
        juju_stat_parser = FileParser(pipeline_deploy_path, 'juju_status.yaml')
        for err in juju_stat_parser.status:
            self.cli.LOG.error(err)

        for key in juju_stat_parser.bsnode:
            self.bsnode[key] = juju_stat_parser.bsnode[key]
        
        self.oil_df = juju_stat_parser.oil_df

        matching_bugs, build_status = self.bug_hunt(pipeline_deploy_path)
        self.yaml_dict = self.add_to_yaml(matching_bugs, build_status,
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
        self.message = deploy.message

        # Process downloaded data:
        self.process_prepare_data()

    def process_prepare_data(self):
        """ Parses the artifacts files from a single pipeline into data and
            metadata.

        """
        prepare_path = os.path.join(self.cli.reportdir, 'pipeline_prepare',
                                    self.build_number)

        # Read console:
        self.process_console_data(prepare_path)

        matching_bugs, build_status = self.bug_hunt(prepare_path)
        self.yaml_dict = self.add_to_yaml(matching_bugs, build_status,
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
        self.message = prepare.message

        # Process downloaded data:
        self.process_tempest_data()

    def process_tempest_data(self):
        """
        Parses the artifacts files from a single pipeline into data and
        metadata

        """
        tts_path = os.path.join(self.cli.reportdir, 'test_tempest_smoke',
                                self.build_number)

        # Read console:
        self.process_console_data(tts_path)

        matching_bugs, build_status = \
            self.bug_hunt(tts_path)
        self.yaml_dict = self.add_to_yaml(matching_bugs, build_status,
                                          self.yaml_dict)
