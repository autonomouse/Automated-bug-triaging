
from crude_common import Common

import os
import re
import yaml
import tarfile
import uuid
import special_cases
from lxml import etree
from jenkinsapi.jenkins import Jenkins as JenkinsAPI
from doberman.common import pycookiecheat
from jenkinsapi.custom_exceptions import *


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
                self.cli.LOG.error(msg)
                raise Exception(msg)

    def pipeline_check(self, pipeline_id):
        return [8, 4, 4, 4, 12] == [len(x) for x in pipeline_id.split('-')]

    def get_triage_data(self, build_num, job, reportdir):
        """ Get the artifacts from jenkins via jenkinsapi object. """
        jenkins_job = self.jenkins_api[job]
        build = jenkins_job.get_build(int(build_num))
        outdir = os.path.join(self.cli.reportdir, job, str(build_num))
        self.cli.LOG.info('Downloading debug data to: %s' % (outdir))
        # Check to make sure it is not still running!:
        if build._data['duration'] == 0:
            return True  # Still running
        try:
            os.makedirs(outdir)
        except OSError:
            if not os.path.isdir(outdir):
                raise
        with open(os.path.join(outdir, "console.txt"), "w") as cnsl:
            self.cli.LOG.info('Saving console @ {0} to {1}'.format(
                              build.baseurl, outdir))
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

    def process_console_data(self, pipeline_path):

        console_location = os.path.join(pipeline_path, 'console.txt')
        cons_txt, self.yaml_dict = self.get_txt(console_location,
                                                self.yaml_dict)
        try:
            self.bsnode
        except:
            self.bsnode = {}
        try:
            self.bsnode['openstack release'] = \
                cons_txt.split('OPENSTACK_RELEASE=')[1].split('\n')[0]
        except:
            self.bsnode['openstack release'] = 'Unknown'

        try:
            self.bsnode['jenkins'] = \
                cons_txt.split('\n')[1].split(' in workspace /var/lib/')[0]
        except:
            self.bsnode['jenkins'] = 'Unknown'

    def get_yaml(self, file_location, yaml_dict):
        return self.get_from_file(file_location, yaml_dict, ftype='yaml')

    def get_txt(self, file_location, yaml_dict):
        return self.get_from_file(file_location, yaml_dict, ftype='text')

    def get_from_file(self, file_location, yaml_dict, ftype='yaml'):
        try:
            with open(file_location, "r") as f:
                if ftype == 'yaml':
                    return (yaml.load(f), yaml_dict)
                else:
                    return (f.read(), yaml_dict)
        except IOError, e:
            fname = file_location.split('/')[-1]
            self.cli.LOG.error("%s: %s is not in artifacts folder (%s)"
                               % (self.pipeline, fname, e[1]))
            msg = fname + ' MISSING'
            yaml_dict = self.non_db_bug(special_cases.bug_dict[fname],
                                        yaml_dict, msg)
            return (None, yaml_dict)

    def dictator(self, dictionary, dkey, dvalue):
        """ Adds dvalue to list in a given dictionary (self.oil_df/oil_nodes).
            Assumes that dictionary will be self.oil_df, self.oil_nodes, etc so
            nothing is returned.

        """

        if dkey not in dictionary:
            dictionary[dkey] = []
        dictionary[dkey].append(dvalue)

    def bug_hunt(self, path):
        """ Using information from the bugs database, opens target file and
            searches the text for each associated regexp. """
        # TODO: As it stands, files are only searched if there is an entry in
        # the DB. This shouldn't be a problem if there is always a dummy bug in
        # the DB for the important files such as console and tempest_xunit.xml
        # FOR EACHJOB TYPE (i.e. pipeline_deploy, pipeline_prepare and
        # test_tempest_smoke).

        parse_as_xml = self.cli.xmls
        build_details = [build_info for build_info in self.jenkins.jenkins_api
                         [self.jobname]._poll()['builds'] if build_info
                         ['number'] == int(self.build_number)][0]
        build_status = (build_details['result'] if 'result' in build_details
                        else 'Unknown')
        matching_bugs = {}
        link2 = ''

        bug_unmatched = True
        if not self.bugs:
            raise Exception("No bugs in database!")
        for bug_id in self.bugs.keys():
            info = {}
            if self.jobname in self.bugs[bug_id]:
                # Any dict in self.bugs[bug_id][self.jobname] can match (or):
                or_dict = self.bugs[bug_id][self.jobname]
                for and_dict in or_dict:
                    # Within the dictionary all have to match (and):
                    hit_dict = {}
                    # Load up file for each target_file in the DB for this bug:
                    for target_file in and_dict.keys():
                        target_location = os.path.join(path, target_file)
                        try:
                            for bssub in self.bsnode:
                                if 'bootstrap_node' not in info:
                                    info['bootstrap_node'] = {}
                                info['bootstrap_node'][bssub] =\
                                    self.bsnode[bssub]
                        except:
                            pass
                        if not os.path.isfile(target_location):
                            info['error'] = target_file + " not present"
                            break
                        if target_file == 'console.txt':
                            link2 = '/job/%s/%s/console' % (self.jobname,
                                                            self.build_number)
                        else:
                            link2 = ('/job/%s/%s/artifact/artifacts/%s'
                                     % (self.jobname, self.build_number,
                                        target_file))
                        if not (target_file in parse_as_xml):
                            with open(target_location, 'r') as grep_me:
                                text = grep_me.read()
                            hit = self.rematch(and_dict, target_file, text)
                            if hit:
                                hit_dict = self.join_dicts(hit_dict, hit)
                                self.message = 0
                            else:
                                info['target file'] = target_file
                                if not self.cli.reduced_output_text:
                                    info['text'] = text
                        else:
                            # Get tempest results:
                            p = etree.XMLParser(huge_tree=True)
                            et = etree.parse(target_location, parser=p)
                            doc = et.getroot()
                            errors_and_fails = doc.xpath('.//failure')
                            errors_and_fails += doc.xpath('.//error')
                            # TODO: There is not currently a way to do multiple
                            # 'and' regexps within a single tempest file - you
                            # can do console AND tempest or tempest OR tempest,
                            # but not tempest AND tempest. Needs it please!
                            for num, fail in enumerate(errors_and_fails):
                                pre_log = fail.get('message')\
                                    .split("begin captured logging")[0]
                                hit = self.rematch(and_dict, target_file,
                                                   pre_log)
                                info['target file'] = target_file
                                info['xunit class'] = \
                                    fail.getparent().get('classname')
                                info['xunit name'] = \
                                    fail.getparent().get('name')
                                if hit:
                                    hit_dict = self.join_dicts(hit_dict, hit)
                                    break
                                else:
                                    if not self.cli.reduced_output_text:
                                        info['text'] = pre_log

                    if and_dict == hit_dict:
                        matching_bugs[bug_id] = \
                            {'regexps': hit_dict,
                             'vendors': self.oil_df['vendor'],
                             'machines': self.oil_df['node'],
                             'units': self.oil_df['service'],
                             'charms': self.oil_df['charm'],
                             'ports': self.oil_df['ports'],
                             'states': self.oil_df['state'],
                             'slaves': self.oil_df['slaves']}
                        if info:
                            matching_bugs[bug_id]['additional info'] = \
                                info
                        self.cli.LOG.info("Bug found!")
                        self.cli.LOG.info(hit_dict)
                        hit_dict = {}
                        bug_unmatched = False
                        break
        if bug_unmatched and (build_status == 'FAILURE' or
                              build_status == 'Unknown'):
            bug_id = 'unfiled-' + str(uuid.uuid4())
            matching_bugs[bug_id] = {'regexps':
                                     'NO REGEX - UNFILED/UNMATCHED BUG',
                                     'vendors': self.oil_df['vendor'],
                                     'machines': self.oil_df['node'],
                                     'units': self.oil_df['service'],
                                     'charms': self.oil_df['charm'],
                                     'ports': self.oil_df['ports'],
                                     'states': self.oil_df['state'],
                                     'slaves': self.oil_df['slaves']}
            self.cli.LOG.info("Unfiled bug found!")
            hit_dict = {}
            self.message = 1
            if info:
                matching_bugs[bug_id]['additional info'] = info
        else:
            self.message = 0
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

        # Read console:
        self.process_console_data(pipeline_deploy_path)

        # Read oil nodes file:
        oil_node_location = os.path.join(pipeline_deploy_path, 'oil_nodes')
        oil_nodes_yml, self.yaml_dict = self.get_yaml(oil_node_location,
                                                      self.yaml_dict)
        if oil_nodes_yml:
            for key in oil_nodes_yml['oil_nodes'][0].keys():
                [self.dictator(self.oil_nodes, key, node[key])
                 for node in oil_nodes_yml['oil_nodes']]

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
        self.bsnode['machine'] = machine
        self.bsnode['state'] = state

        row = 0
        for service in juju_status['services']:
            serv = juju_status['services'][service]
            charm = serv['charm'] if 'charm' in serv else 'Unknown'
            if 'units' in serv:
                units = serv['units']
            else:
                units = {}
                self.dictator(self.oil_df, 'node', 'N/A')
                self.dictator(self.oil_df, 'service', 'N/A')
                self.dictator(self.oil_df, 'vendor', 'N/A')
                self.dictator(self.oil_df, 'charm', charm)
                self.dictator(self.oil_df, 'ports', 'N/A')
                self.dictator(self.oil_df, 'state', 'N/A')
                self.dictator(self.oil_df, 'slaves', 'N/A')

            for unit in units:
                this_unit = units[unit]
                ports = ", ".join(this_unit['open-ports']) if 'open-ports' \
                    in this_unit else "N/A"
                machine_no = this_unit['machine'].split('/')[0]
                host_name = (this_unit['public-address'] if 'public-address' in
                             this_unit else 'Unknown')
                machine_info = juju_status['machines'][machine_no]
                use_alternative_hw_lookup = False
                if self.oil_nodes:
                    try:
                        node_idx = self.oil_nodes['host'].index(host_name)
                        hardware = [hw.split('hardware-')[1] for hw in
                                    self.oil_nodes['tags'][node_idx]
                                    if 'hardware-' in hw]
                        slave = ", ".join([str(slv) for slv in
                                          self.oil_nodes['tags'][node_idx]
                                          if 'slave-' in slv])
                    except:
                        use_alternative_hw_lookup = True
                else:
                    use_alternative_hw_lookup = True
                if use_alternative_hw_lookup:
                    if 'hardware' in machine_info:
                        hardware = [hw.split('hardware-')[1] for hw in
                                    machine_info['hardware'].split('tags=')
                                    [1].split(',') if 'hardware-' in hw]
                        slave = ", ".join([str(slv) for slv in machine_info
                                           ['hardware'].split('tags=')[1]
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
                        # TODO: Need to find a way to identify
                        # which container is being used here:
                        container = []
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
                self.dictator(self.oil_df, 'node', machine)
                self.dictator(self.oil_df, 'service', unit)
                self.dictator(self.oil_df, 'vendor', ', '.join(hardware))
                self.dictator(self.oil_df, 'charm', charm)
                self.dictator(self.oil_df, 'ports', ports)
                self.dictator(self.oil_df, 'state', state)
                self.dictator(self.oil_df, 'slaves', slave)
                row += 1
        else:  # Oh look, Python lets you put elses after for statements...
            self.dictator(self.oil_df, 'node', 'N/A')
            self.dictator(self.oil_df, 'service', 'N/A')
            self.dictator(self.oil_df, 'vendor', 'N/A')
            self.dictator(self.oil_df, 'charm', 'N/A')
            self.dictator(self.oil_df, 'ports', 'N/A')
            self.dictator(self.oil_df, 'state', 'N/A')
            self.dictator(self.oil_df, 'slaves', 'N/A')
        matching_bugs, build_status, link = self.bug_hunt(pipeline_deploy_path)
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

        matching_bugs, build_status, link = self.bug_hunt(prepare_path)
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

        matching_bugs, build_status, link = \
            self.bug_hunt(tts_path)
        self.yaml_dict = self.add_to_yaml(matching_bugs, build_status, link,
                                          self.yaml_dict)
