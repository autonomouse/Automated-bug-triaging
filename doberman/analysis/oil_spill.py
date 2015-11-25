import os
import fnmatch
from lxml import etree
from doberman.common.base import DobermanBase
from jenkinsapi.custom_exceptions import *
import re
import uuid
from jenkinsapi.custom_exceptions import *
from glob import glob
# <ACTIONPOINT>
try:
    from weeblclient.weebl_python2.weebl import Weebl
    from weeblclient.weebl_python2.exception import (
        UnexpectedStatusCode, InstanceAlreadyExists)
except ImportError as e:
    pass
#


class OilSpill(DobermanBase):
    """Failure detection class"""

    def __init__(self, build_number, jobname, yaml_dict, cli, pipeline):
        self.cli = cli
        self.build_number = build_number
        self.jobname = jobname
        self.yaml_dict = yaml_dict
        self.pipeline = pipeline
        # <ACTIONPOINT>
        if self.cli.use_weebl:
            self.weebl = Weebl(
                self.cli.uuid,
                self.cli.environment,
                username=self.cli.weebl_username,
                apikey=self.cli.weebl_apikey,
                weebl_url=self.cli.weebl_url)
        #

    def bug_hunt(self, path, announce=True):
        """ Using information from the bugs database, opens target file and
            searches the text for each associated regexp. """
        # TODO: As it stands, files are only searched if there is an entry in
        # the DB. This shouldn't be a problem if there is always a dummy bug in
        # the DB for the important files such as console and tempest_xunit.xml
        # FOR EACH JOB TYPE (i.e. pipeline_deploy, pipeline_prepare and
        # test_tempest_smoke).
        info = {}
        parse_as_xml = self.cli.xmls
        xml_files_parsed = []

        if not self.cli.offline_mode:
            build_details_list =\
                [build_info for build_info in self.jenkins.jenkins_api
                 [self.jobname]._poll()['builds']
                 if build_info['number'] == int(self.build_number)]
            if build_details_list != []:
                build_details = build_details_list[0]
            else:
                build_details = {}

            build_status = (build_details['result'] if 'result' in
                            build_details else 'Unknown')
        else:
            build_status = 'Unknown'
        matching_bugs = {}
        # <ACTIONPOINT>
        if self.cli.use_weebl:
            if not self.cli.offline_mode:
                timestamp = build_details.get('timestamp')
            else:
                timestamp = None

            # Create/Update build:
            params = (self.build_number, self.pipeline, self.jobname,
                      build_status.lower())
            try:
                self.build_uuid = self.weebl.create_build(
                    *params, build_finished_at=timestamp)
            except InstanceAlreadyExists as e:
                self.build_uuid = self.weebl.update_build(
                    *params, build_finished_at=timestamp)
            except UnexpectedStatusCode as e:
                raise(e)
        #
        bug_unmatched = True
        if not self.cli.bugs:
            raise Exception("No bugs in database!")

        unfiled_xml_fails = {}
        failed_to_hit_any_flag = True

        for bug_id, bug_info in self.cli.bugs.items():
            if self.jobname in self.cli.bugs[bug_id]:
                # <ACTIONPOINT>
                if self.cli.use_weebl:
                    self.regex_uuid = bug_info['regex_uuid']
                #
                # Any dict in self.cli.bugs[bug_id][self.jobname] can match(or)
                or_dict = self.cli.bugs[bug_id][self.jobname]
                files_to_scan = []

                [files_to_scan.extend(and_dict.keys()) for and_dict in or_dict]
                xmls_to_scan = set([xml for xml in files_to_scan if xml in
                                    self.cli.xmls])
                for and_dict in or_dict:
                    # Within the dictionary all have to match (and):
                    hit_dict = {}
                    glob_hits = []
                    # Load up file for each target_file in the DB for this bug:
                    for target_file in and_dict.keys():
                        if target_file == "console.txt":
                            target_file = "{}_console.txt".format(self.jobname)
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
                            if fnmatch.fnmatch(target, parse_as_xml):
                                with open(target_location, 'r') as grep_me:
                                    text = grep_me.read()
                                hit = self.rematch(and_dict, target,
                                                   target_file, text)
                                if hit:
                                    failed_to_hit_any_flag = False
                                    glob_hits.append(
                                        target_location.split('/')[-1])
                                    hit_dict = self.join_dicts(hit_dict, hit)
                                    self.message = 0
                                else:
                                    failed_to_hit_any_flag = True

                            else:
                                if target in xmls_to_scan:
                                    xmls_to_scan.remove(target)
                                if target in xml_files_parsed:
                                    xml_unparsed = False
                                else:
                                    xml_unparsed = True
                                    xml_files_parsed.append(target)
                                # Get tempest results:
                                p = etree.XMLParser(huge_tree=True)
                                try:
                                    et = etree.parse(target_location, parser=p)
                                    doc = et.getroot()
                                except etree.XMLSyntaxError as e:
                                    msg = "Cannot read from XML file"
                                    self.cli.LOG.error(msg)
                                    continue
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
                                    info['xunit class'] =\
                                        fail.getparent().get('classname')
                                    info['xunit name'] =\
                                        fail.getparent().get('name')
                                    hit = self.rematch(and_dict, target,
                                                       target_file, pre_log)
                                    if hit:
                                        failed_to_hit_any_flag = False
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

                    if failed_to_hit_any_flag:
                        # xml or not, if not hits return console in info:
                        default_target = '{}_console.txt'.format(self.jobname)
                        info['target file'] = default_target
                        target_location = os.path.join(path, default_target)

                        current_target = target if 'target' in locals() else \
                            None
                        text = text if 'text' in locals() else None
                        try:
                            if not text or current_target != default_target:
                                # reload the text:
                                with open(target_location, 'r') as grep_me:
                                    text = grep_me.read()
                            info['text'] = text
                        except IOError as e:
                            info['text'] = None
                            self.cli.LOG.error(e)

                    # Recreate original_hit_dict (i.e. with keys as
                    # 'console.txt' rather than 'pipeline_deploy_console.txt'
                    # as I changed it to):
                    d1 = [("console.txt", v) for k, v in hit_dict.items()
                          if "_console.txt" in k]
                    d2 = [(k, v) for k, v in hit_dict.items()
                          if "_console.txt" not in k]
                    original_hit_dict = dict(d1 + d2)

                    if and_dict == original_hit_dict:
                        links = []
                        url = self.cli.external_jenkins_url
                        if (not glob_hits) and (target_file in parse_as_xml):
                            glob_hits = [target_file]
                        for hit_file in glob_hits:
                            if "console.txt" in hit_file:
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
                        # Only stop if there are not still xml files to scan:
                        if len(xmls_to_scan) < 1:
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
            self.message = 0
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

    def rematch(self, bugs, target_file, orig_filename_in_db, text):
        """ Search files in bugs for multiple matching regexps. """
        if target_file == "{}_console.txt".format(self.jobname):
            orig_filename_in_db = "console.txt"
        target_bugs = bugs.get(orig_filename_in_db, bugs.get('*'))
        if not target_bugs:
            return
        regexps = target_bugs.get('regexp')

        if type(regexps) == list:
            if len(regexps) > 1:
                regexp = '|'.join(regexps)
                set_re = set([regexp])
            else:
                regexp = regexps[0]
                set_re = set(regexps)
        else:
            regexp = regexps
            set_re = set([regexps])

        if regexp not in ['None', None, '']:
            matches = re.compile(regexp, re.DOTALL).findall(text)
            if matches:
                if len(set(matches)) >= len(set_re):

                    # <ACTIONPOINT>
                    if self.cli.use_weebl:
                        # Create bug occurrence:
                        try:
                            self.weebl.create_bugoccurrence(self.build_uuid,
                                                            self.regex_uuid)
                        except InstanceAlreadyExists as e:
                            pass
                        except UnexpectedStatusCode as e:
                            raise(e)
                    #

                    if '*' in orig_filename_in_db:
                        return {orig_filename_in_db: {'regexp': regexps}}
                    else:
                        return {target_file: {'regexp': regexps}}

    def oil_survey(self, path, pipeline, extracted_info):
        self.oil_df = extracted_info['oil_df']
        (matching_bugs, build_status) = self.bug_hunt(path)
        self.matching_bugs = matching_bugs
        return self.matching_bugs
