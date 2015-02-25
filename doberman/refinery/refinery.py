#! /usr/bin/env python2

import sys
import os
import yaml
import json
import operator
import re
import tempfile
import shutil
import hashlib
from jenkinsapi.custom_exceptions import *
from doberman.analysis.analysis import CrudeAnalysis
from doberman.analysis.crude_jenkins import Jenkins
from doberman.analysis.crude_test_catalog import TestCatalog
from plotting import Plotting
from difflib import SequenceMatcher
from cli import CLI


class Refinery(CrudeAnalysis):
    """
    A post-analysis class that processes the yaml output file from
    CrudeAnalysis and collates number of machine affected by each bug, provides
    percentages of failures that are auto-triaged successfully and will
    hopefully determine if crude is working (a.k.a. "Doberman metrics"). It
    will produce a list of 'known associates' - bugs that are frequently found
    together in the same failure to help with triage and identifying root
    causes of failure.

    """

    def __init__(self):
        """ Overwriting CrudeAnalysis' __init__ method """

        self.message = -1
        self.tmpdir = tempfile.mkdtemp()

        self.cli = CLI()
        self.all_build_numbers = []
        self.bug_rankings = {}
        self.pipelines_affected_by_bug = {}
        self.grouped_bugs = {}
        self.bug_rankings = {}
        self.all_scores = {}

        # Download and analyse the crude output yamls:
        self.analyse_crude_output()

        # Tidy Up:
        if not self.cli.keep_data:
            self.remove_dirs(self.all_build_numbers)
            [os.remove(os.path.join(self.cli.reportdir, bdict)) for bdict in 
             os.listdir(self.cli.reportdir) if 'bugs_dict_' in bdict]
        shutil.rmtree(self.tmpdir)

    def analyse_crude_output(self):
        """ Get and analyse the crude output yamls.
        """

        # Get crude output:
        marker = 'triage'
        self.jenkins = Jenkins(self.cli)
        if not self.cli.offline_mode:
            self.test_catalog = TestCatalog(self.cli)
            self.build_numbers = self.build_pl_ids_and_check()
            self.download_triage_files(self.cli.crude_job, marker,
                                       self.cli.reportdir)
        else:
            self.cli.LOG.info("*** Offline mode is on. ***")
            self.cli.op_dir_structure = self.determine_folder_structure()
        self.cli.LOG.info("Working on {0} as refinery input directory"
                          .format(self.cli.reportdir))

        # Analyse the downloaded crude output yamls:
        other_jobs = [j for j in self.cli.job_names if j != self.cli.crude_job]
        previous_pls_affected = {}
        for job in other_jobs:
            self.cli.LOG.info("Unifying {} data.".format(job))
            self.unify_downloaded_triage_files(job, self.cli.crude_job, marker)
            matching_bugs_dicts = [bdict for bdict in os.listdir(
                                   self.cli.reportdir) if 'bugs_dict_' in bdict
                                   and job in bdict]
            for pos, fn in enumerate(matching_bugs_dicts):
                self.cli.LOG.info("Generating job specific bugs file: {}"
                                  .format(fn))
                # Load up the data from file:
                job_specific_bugs = self.load_bugs_dict(fn)

                self.grouped_bugs, self.all_scores = \
                    self.group_similar_unfiled_bugs(job, job_specific_bugs)
                pls_affected = self.calculate_bug_prevalence(self.grouped_bugs,
                                                  job_specific_bugs)

                # Keep previous for merging:
                previous_pls_affected = pls_affected
                previous_grouped_bugs = self.grouped_bugs
                previous_bug_rankings = self.bug_rankings
                previous_all_scores = self.all_scores  # Is this even used?

                self.pipelines_affected_by_bug = \
                    self.join_dicts(previous_pls_affected, pls_affected)

                if pos > 1:
                    self.grouped_bugs = self.join_dicts(self.grouped_bugs,
                                                        previous_grouped_bugs)
                    self.bug_rankings = self.join_dicts(self.bug_rankings,
                                                      previous_bug_rankings)
                    # Is all_scores even used?
                    self.all_scores = self.join_dicts(self.all_scores,
                                                      previous_all_scores)
            self.generate_yamls(job)
            # TODO: Merging multiple sub-jobs back into a single jobs file:
            # open a new file and stream each yaml dump of the bugs dict
            # into it. I'm not sure if this will get around the memory issue
            # or not. Need to investigate. This might help:
            # http://stackoverflow.com/questions/1033424/how-to-remove-bad-path-characters-in-python
        self.report_top_ten_bugs(other_jobs, self.bug_rankings)

        try:
            self.plot = Plotting(self.bug_rankings, self.cli)
        except:
            self.cli.LOG.info("Unable to generate plots.")

        if 'pipeline_ids' in self.__dict__:
            self.log_pipelines()

    def determine_folder_structure(self):
        """ Set directory structure for downloads, where 0 is reportdir, 1 is
            job name and 2 is build number.
        """
        crude_folder = os.path.join(self.cli.reportdir, self.cli.crude_job)

        if not os.path.exists(self.cli.reportdir):
            emsg = "Directory doesn't exist! {}".format(self.cli.reportdir)
            self.cli.LOG.error(emsg)
            raise Exception(emsg)
        else:
            other_jobs = [j for j in self.cli.job_names if j !=
                          self.cli.crude_job]
            for job in other_jobs:
                if os.path.exists(crude_folder):
                    return os.path.join("{0}", "{3}", "{2}")
                else:
                    return os.path.join("{0}", "{1}", "{2}")

    def generate_yamls(self, job=None, path=None):
        """
            Write data to output yaml files.
        """
        if not path:
            path = self.cli.reportdir
        self.generate_pl_bug_fx_yaml(path)
        self.generate_unfiled_bugs_yaml(path)
        self.generate_all_scores_yaml(path)
        if job:
            self.generate_bug_ranking_yaml(path, job)

    def generate_pl_bug_fx_yaml(self, path):
        self.write_output_yaml(path, 'pipelines_affected_by_bug.yml',
                               self.pipelines_affected_by_bug)

    def generate_unfiled_bugs_yaml(self, path):
        self.write_output_yaml(path, 'auto-triaged_unfiled_bugs.yml',
                               {'pipelines': self.grouped_bugs})

    def generate_all_scores_yaml(self, path):
        self.write_output_yaml(path, 'all_scores.yml',
                               {'pipelines': self.all_scores})

    def generate_bug_ranking_yaml(self, path, job=None):
        if job == 'all':
            for job in self.bug_rankings:
                self.generate_individual_bug_ranking_yaml(path, job)
        else:
            self.generate_individual_bug_ranking_yaml(path, job)

    def generate_individual_bug_ranking_yaml(self, path, job):
        bug_rank = self.bug_rankings.get(job)
        try:
            fn = 'bug_ranking_{}.yml'.format(job)
            self.write_output_yaml(path, fn, bug_rank)
        except:
            emsg = "No such file {} in {}".format(fn, path)
            self.cli.LOG.error(emsg)
            raise Exception(emsg)

    def generate_bugs_json(self, data, job, sfx=None, path=None, 
                           verbose=True):
        if not path:
            path = self.cli.reportdir
        if not sfx:
            suffix = job
        else:
            suffix = "{}_{}".format(job, sfx)
        self.write_output_json(path, 'bugs_dict_{}.json'.format(suffix),
                               {'pipelines': data}, verbose=verbose)

    def download_specific_file(self, job, pipeline_id, build_num, marker,
                               outdir, rename=False):
        """ Download a particular artifact from jenkins. """

        jenkins_job = self.jenkins.jenkins_api[job]
        build = jenkins_job.get_build(int(build_num))
        artifact_found = False

        if build._data['duration'] == 0:
            msg = "Output from {} unavailable (build {}) - still running?"
            self.cli.LOG.info(msg.format(pipeline_id))
            return

        self.mkdir(outdir)

        if marker == 'console.txt':
            self.jenkins.write_console_to_file(build, outdir)
            artifact_found = True
            if rename:
                rn_from = os.path.join(outdir, marker)
                rn_to = os.path.join(outdir, rename)
                os.rename(rn_from, rn_to)
                self.cli.LOG.info("{0} file saved to {1} as {2}"
                                  .format(marker, outdir, rn_to))
            else:
                self.cli.LOG.info("{0} file saved to {1}"
                                  .format(marker, outdir))
        else:
            for artifact in build.get_artifacts():
                artifact_found = False
                if marker in str(artifact):
                    artifact_found = True
                    artifact.save_to_dir(outdir)
                    # TODO: Would these ever need renaming?

        if not artifact_found:
            msg = ("No triage artifacts found for job {0} for {1}"
                   .format(job, pipeline_id))
            self.cli.LOG.info(msg)

    def download_triage_files(self, job, marker, output_folder):
        """
        Get crude output
        """
        self.cli.op_dir_structure = os.path.join("{0}", "{3}", "{2}")
        self.all_build_numbers = []
        build_numbers = self.test_catalog.get_all_pipelines(self.pipeline_ids)

        for pipeline_id in self.pipeline_ids:
            try:
                build_num = build_numbers[pipeline_id].get(job)

                if build_num:
                    outdir = (self.cli.op_dir_structure.format(
                              self.cli.reportdir, job, str(build_num),
                              self.cli.crude_job))
                    self.all_build_numbers.append(build_num)
                    self.download_specific_file(job, pipeline_id, build_num,
                                                marker, outdir)
                else:
                    self.cli.LOG.info("No build number found: job {0} for {1}"
                                      .format(job, pipeline_id))
            except Exception, e:
                self.cli.LOG.error("Error downloading pipeline {0} ({1}) - {2}"
                                   .format(job, pipeline_id, e))

    def move_artifacts_from_crude_job_folder(self, marker):
        """ """

        crude_job = self.cli.crude_job

        if crude_job in os.walk(self.cli.reportdir).next()[1]:
            path_to_crude_folder = os.path.join(self.cli.reportdir, crude_job)
            for build_num in os.walk(path_to_crude_folder).next()[1]:
                bpath = os.path.join(path_to_crude_folder, build_num)
                other_jobs = [j for j in self.cli.job_names if j != crude_job]
                pipelines = [x for x in self.build_numbers if
                             self.build_numbers[x].get(crude_job) == build_num]
                pipeline = pipelines[0]  # There can be only one...
                for job in other_jobs:
                    filename = "{0}_{1}.yml".format(marker, job)
                    if os.path.exists(os.path.join(bpath, filename)):
                        src_file = os.path.join(bpath, filename)
                        job_pl = self.build_numbers[pipeline].get(job)
                        if job_pl:
                            newpath = os.path.join(self.cli.reportdir, job,
                                                   job_pl)
                            self.mkdir(newpath)
                            dst_file = os.path.join(newpath, filename)
                            shutil.move(src_file, dst_file)
        # TODO: Check if empty
        shutil.rmtree(path_to_crude_folder)

    def unify_downloaded_triage_files(self, job, crude_job, marker):
        """
        Unify the downloaded crude output yamls into a single dictionary.

        """

        bug_dict = {}
        self.units = []

        if job in self.cli.multi_bugs_in_pl:
            multi_bugs_per_pl = True
        else:
            multi_bugs_per_pl = False

        crude_folder = os.path.join(self.cli.reportdir, crude_job)
        if not os.path.exists(self.cli.reportdir):
            self.cli.LOG.error("{0} doesn't exist!".format(crude_folder))
        else:
            filename = "{0}_{1}.yml".format(marker, job)
            skip = False
            scan_sub_folder = False
            
            if os.path.exists(crude_folder):
                if filename in os.listdir(crude_folder):
                    # If they're in the top level directory, just do this:
                    bug_dict = self.unify_and_join(bug_dict, crude_job, marker,
                                                   job, filename, crude_folder,
                                                   multi_bugs_per_pl)
                else:
                    scan_sub_folder = True
            elif filename in os.listdir(self.cli.reportdir):
                # If they're in the top level directory, just do this...:
                bug_dict = (self.unify_and_join(bug_dict, crude_job, marker,
                            job, filename, self.cli.reportdir,
                            multi_bugs_per_pl))
            else:
                skip = True
                self.cli.LOG.error("Cannot find {} in {} - skipping"
                                   .format(filename, self.cli.reportdir))

            if scan_sub_folder:
                # ...otherwise, scan the sub-folders:
                self.build_class_and_unit_list(filename, crude_folder,
                                               multi_bugs_per_pl)

                if multi_bugs_per_pl:
                    msg = "Reprocessing XML data from {} discrete builds into "
                    msg += "{} new file(s)"
                    self.cli.LOG.info(msg.format(len(os.listdir(crude_folder)),
                                      len(self.x_classes_and_units)))

                for build_num in os.walk(crude_folder).next()[1]:
                    # For each save an output file...
                    for num, xml_check in enumerate(self.x_classes_and_units):
                        bug_dict = (self.unify_and_join(bug_dict, crude_job,
                                    marker, job, filename, crude_folder,
                                    multi_bugs_per_pl, xml_check, build_num))
                        if multi_bugs_per_pl:
                            # Notify user of progress:
                            prog = (self.calculate_progress(num,
                                    self.x_classes_and_units, 5))
                            if prog:
                                self.cli.LOG.info("Reprocessing {}% complete"
                                                  .format(prog))

            if not multi_bugs_per_pl:
                self.generate_bugs_json(bug_dict, job)

            if not skip:
                self.cli.LOG.info("{} data unified.".format(job))

    def unify_and_join(self, bug_dict, crude_job, marker, job, filename,
                       crude_folder, multi_bugs_per_pl, xml_check=None,
                       build_num=None):
        new_bugs = self.unify(crude_job, marker, job, filename, crude_folder,
                              xml_check, build_num)
        bug_dict = self.join_dicts(bug_dict, new_bugs)
        if multi_bugs_per_pl:
            suffix = xml_check[0].split('.')[-1] + xml_check[1]
            self.generate_bugs_json(bug_dict, job, suffix, verbose=False)
        else:
            self.generate_bugs_json(bug_dict, job, verbose=False)
        return bug_dict


    def build_class_and_unit_list(self, filename, rdir, multi_bugs_per_pl):
        """
            Get list of classes and names for xml file or return false
        """

        self.x_classes_and_units = []
        if multi_bugs_per_pl:
            for build_num in os.walk(rdir).next()[1]:
                file_location = os.path.join(rdir, str(build_num), filename)
                try:
                    with open(file_location, "r") as f:
                        yaml_content = yaml.load(f)
                        content = yaml_content
                except:
                    self.cli.LOG.error("Problem fetching data from {}"
                                       .format(file_location))
                    content = {}
                output = content.get('pipeline')

                if output:
                    for pipeline_id in output:
                        x_class_unit = None
                        for bug in output[pipeline_id]['bugs']:
                            xcu = (output[pipeline_id]['bugs'][bug]
                                   ['additional info'] if output[pipeline_id]
                                   ['bugs'][bug].get('additional info') else
                                   None)
                            if xcu:
                                if (xcu.get('xunit class') and
                                    xcu.get('xunit name')):
                                    x_class_unit = (xcu['xunit class'],
                                                    xcu['xunit name'])
                        if x_class_unit:
                            self.x_classes_and_units.append(x_class_unit)
            self.x_classes_and_units = list(set(self.x_classes_and_units))
        else:
            self.x_classes_and_units = [False]

    def unify(self, crude_job, marker, job, filename, rdir, xml_check=False,
              build_num=None):
        """
            Unify the downloaded crude output yamls into a single dictionary.

        """

        if build_num:
            file_location = os.path.join(rdir, str(build_num), filename)
        else:
            file_location = os.path.join(rdir, filename)
        # Read in each yaml output file:
        try:
            with open(file_location, "r") as f:
                yaml_content = yaml.load(f)
                output = yaml_content.get('pipeline')
        except:
            output = None

        # Combine all yamls by pipeline:
        bug_dict = {}
        if output:
            for pipeline_id in output:
                matching_class_unit = None
                x_class_unit = None
                if xml_check:
                    x_class_unit = None
                    for bug in output[pipeline_id]['bugs']:
                        xcu = (output[pipeline_id]['bugs'][bug]
                               ['additional info'] if output[pipeline_id]
                               ['bugs'][bug].get('additional info') else None)
                        if xcu:
                            if (xcu.get('xunit class') and xcu.get
                                ('xunit name')):
                                x_class_unit = (xcu['xunit class'],
                                                xcu['xunit name'])
                        if x_class_unit != xml_check:
                            x_class_unit = None
                        else:
                            matching_class_unit = x_class_unit
                            break
                    if not matching_class_unit:
                        return bug_dict

                if not bug_dict.get(pipeline_id):
                    bug_dict[pipeline_id] = {}

                # Add bug to bug_dict.
                for bug in output[pipeline_id].get('bugs'):

                    # TODO: Add an "if bug_dict[pipeline_id].get(bug)"
                    # and merge by always picking the latter timestamp,
                    # and the rest of this (until the 'end of would be
                    # else block' below) should be in an else.

                    plop = output[pipeline_id]  # This is all Ryan's fault!

                    bug_output = plop['bugs'][bug]
                    bug_output['pipeline_id'] = pipeline_id
                    j_ts = plop.get('Jenkins timestamp')
                    bug_output['Jenkins timestamp'] = j_ts
                    build = plop.get('build')
                    bug_output['build'] = build
                    status = plop['status']
                    bug_output['status'] = status
                    crude_ts = plop.get('Crude-Analysis timestamp')
                    bug_output['Crude-Analysis timestamp'] = crude_ts
                    link_to_jkns = plop.get('link to jenkins')
                    bug_output['link to jenkins'] = link_to_jkns
                    link_to_tcat = plop.get('link to test-catalog')
                    bug_output['link to test-catalog'] = link_to_tcat
                    bug_output['job'] = job
                    if not build_num:
                        build_num = plop.get('build')
                    if ('unfiled' in bug):
                        op_dir = \
                            (self.cli.op_dir_structure.format(
                             self.cli.reportdir, job, build_num, crude_job))
                        # rename = "{0}_console.txt".format(job)
                        rename = "console.txt"
                        # Check to see if console is present. If not, download:
                        if bug_output['additional info']['target file'] != \
                                'console.txt':
                            bug_output['additional info']['target file'] = \
                                'console.txt'

                            a_file = os.path.join(op_dir, rename)
                            if not os.path.isfile(a_file):
                                params = (job, pipeline_id, build,
                                          'console.txt', op_dir, rename)
                                try:
                                    self.download_specific_file(*params)
                                except Exception, e:
                                    err = "Problem fetching console data for "
                                    err += "pl {} (bug {}). {}"
                                    self.cli.LOG.info(err.format(pipeline_id,
                                                      bug, e))
                                    bug_output['additional info']['text'] = \
                                        None
                            try:
                                openme = os.path.join(op_dir, rename)
                                with open(openme, 'r') as f:
                                    bug_output['additional info']['text'] = \
                                        f.read()
                            except Exception, e:
                                err = "Couldn't open {} for pl {} (bug {}). {}"
                                self.cli.LOG.info(err.format(openme,
                                                  pipeline_id, bug, e))
                                bug_output['additional info']['text'] = None
                    bug_dict[pipeline_id][bug] = bug_output
                    # TODO: end of would be else block
        return bug_dict

    def calculate_bug_prevalence(self, unique_unfiled_bugs, job_specific_bugs):
        """
        calculate_bug_prevalence
        Needs to make charts too...
        """
        self.cli.LOG.info("Analysing the downloaded crude output yamls.")
        bug_prevalence = {'all_bugs': {}}
        pipelines_affected_by_bug = {}

        for bug_no in unique_unfiled_bugs:
            job = unique_unfiled_bugs[bug_no]['job']
            if job not in bug_prevalence:
                bug_prevalence[job] = {}
            bug_prevalence[job][bug_no] = len(unique_unfiled_bugs[bug_no]
                                              ['duplicates'])
            pipelines_affected_by_bug[bug_no] = \
                unique_unfiled_bugs[bug_no]['duplicates']

        for pipeline in job_specific_bugs:
            for bug_no in job_specific_bugs[pipeline]:
                if 'unfiled' not in bug_no:
                    job = job_specific_bugs[pipeline][bug_no]['job']
                    if job not in bug_prevalence:
                        bug_prevalence[job] = {}
                    if bug_no not in bug_prevalence[job]:
                        bug_prevalence['all_bugs'][bug_no] = 1
                        bug_prevalence[job][bug_no] = 1
                    else:
                        bug_prevalence['all_bugs'][bug_no] = \
                            bug_prevalence['all_bugs'][bug_no] + 1
                        bug_prevalence[job][bug_no] = \
                            bug_prevalence[job][bug_no] + 1
                    if bug_no not in pipelines_affected_by_bug:
                        pipelines_affected_by_bug[bug_no] = []
                    pipelines_affected_by_bug[bug_no].append(pipeline)

        for job_or_all in bug_prevalence:
            try:
                bug_rank = sorted(bug_prevalence[job_or_all].items(),
                                  key=operator.itemgetter(1))
                bug_rank.reverse()
            except:
                pass
            self.bug_rankings[job_or_all] = bug_rank

        return (pipelines_affected_by_bug)

    def get_identifying_bug_details(self, bugs, bug_id, multi_bpp=False):
        """ """
        if multi_bpp:
            return self.get_multiple_pipeline_bug_info(bugs, bug_id)
        else:
            return self.get_single_pipeline_bug_info(bugs, bug_id)

    def get_single_pipeline_bug_info(self, bugs, bug_id):
        return self.normalise_bug_details(bugs, bug_id)

    def get_multiple_pipeline_bug_info(self, bugs, bug_id):
        xmlclass, xmlname = self.get_xunit_class_and_name(bugs, bug_id)
        info = bugs[bug_id]['additional info'].get('text')
        bug_feedback = self.normalise_bug_details(bugs, bug_id, info)
        return bug_feedback

    def get_xunit_class_and_name(self, bugs, bug_id):
        """ Make info_a/b equal to xunitclass + xunitname. """
        try:
            addinfo = bugs[bug_id].get('additional info')
            return (addinfo['xunit class'], addinfo['xunit name'])
        except:
            return (None, None)

    def normalise_bug_details(self, bugs, bug_id, info=None):
        """
        get info on bug from additional info. Replace build number,
        pipeline id, date newlines, \ etc with blanks...
        """
        pipelines = [bugs[b].get('pipeline_id') for b in bugs]
        if not info and 'additional info' in bugs[bug_id]:
            info = bugs[bug_id]['additional info'].get('text')

        # replace pipeline id(s) with placeholder:
        pl_placeholder = 'AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'
        for pl in pipelines:
            info.replace(pl, pl_placeholder) if info else ''

        # replace numbers with 'X'
        info = re.sub(r'\d', 'X', info) if info else ''

        # Search for traceback:
        traceback_list = []
        tb_split = info.split('Traceback')
        for tb in tb_split[1:]:
            dt_split = (tb.split('XXXX-XX-XX XX:XX:XX') if tb_split[0] != ''
                        else '')
            this_tb = 'Traceback' + dt_split[0] if dt_split != '' else ''
            traceback_list.append(this_tb)
        traceback = " ".join([str(n) for n in set(traceback_list)])
        errs = ''
        fails = ''
        if not traceback:
            # Search for errors:
            errs = sorted(re.findall('ERROR.*', info))

            # Search for failure:
            fails = sorted(re.findall('fail.*', info, re.IGNORECASE))

        bug_feedback = " ".join([str(n) for n in (traceback, errs, fails)])
        if (bug_feedback == ' [] []') or not bug_feedback.strip(' '):
            return
        else:
            return bug_feedback

    def load_bugs_dict(self, filename, path=None):
        if not path:
            path = self.cli.reportdir
        file_location = os.path.join(path, filename)
        with open(file_location, "r") as f:
            return json.load(f).get('pipelines')

    def group_similar_unfiled_bugs(self, job, unified_bugdict,
                                   max_sequence_size=10000):
        """
            Group unfiled bugs together by similarity of error message. If the
            string to compare is larger than the given max_sequence_size
            (default: 10000 characters) then a md5 hashlib is used to check for
            an exact match, otherwise, SequenceMatcher is used to determine if
            an error is close enough (i.e. greater than the given threshold
            value) to be considered a match.
        """

        self.cli.LOG.info("Grouping unfiled {} bugs by error similarity."
                          .format(job))
        unfiled_bugs = {}

        for pipeline in unified_bugdict:
            for bug_no in unified_bugdict[pipeline]:
                if 'unfiled' in bug_no:
                    unfiled_bugs[bug_no] = unified_bugdict[pipeline][bug_no]

        grouped_bugs = {}
        unique_bugs = {}
        all_scores = {}
        duplicates = {}

        if not unfiled_bugs:
            self.cli.LOG.info("No unfiled {} bugs found!".format(job))
            return (grouped_bugs, all_scores)

        unaccounted_bugs = unfiled_bugs.keys()

        ujob = unfiled_bugs[unaccounted_bugs[0]].get('job')

        if ujob in self.cli.multi_bugs_in_pl:
            multiple_bugs_per_pipeline = True
        else:
            multiple_bugs_per_pipeline = False

        for pos, unfiled_bug in enumerate(unaccounted_bugs):
            info_a = \
                self.get_identifying_bug_details(unfiled_bugs, unfiled_bug,
                                                 multiple_bugs_per_pipeline)

            # Have we seen this bug before?
            for already_seen in unique_bugs:
                info_b = unique_bugs[already_seen]
                if info_a and info_b:
                    if (len(info_a) + len(info_b)) > max_sequence_size:
                        score = -1
                        a_md5 = hashlib.md5()
                        a_md5.update(info_a)
                        b_md5 = hashlib.md5()
                        b_md5.update(info_b)
                        if a_md5.hexdigest() == b_md5.hexdigest():
                            score = 1
                            msg = "{} and {} were over maximum sequence size "
                            msg += "and so were compared using md5 and found "
                            msg += "to be equivalent."
                            self.cli.LOG.info(msg.format(already_seen,
                                                         unfiled_bug))
                        else:
                            score = -1
                    else:
                        score = SequenceMatcher(None, info_a, info_b).ratio()
                else:
                    score = -1
                if multiple_bugs_per_pipeline:
                    threshold = 1.0
                else:
                    threshold = float(self.cli.match_threshold)
                if score >= threshold:
                    if unfiled_bug not in all_scores:
                        all_scores[unfiled_bug] = {}
                    all_scores[unfiled_bug][already_seen] = score
                    duplicates[already_seen].append(unfiled_bug)
                    break
            else:
                unique_bugs[unfiled_bug] = info_a
                duplicates[unfiled_bug] = [unfiled_bug]

            # Notify user of progress:
            progress = self.calculate_progress(pos, unaccounted_bugs)
            if progress:
                self.cli.LOG.info("Bug grouping {}% complete".format(progress))

        self.cli.LOG.info("{} unique bugs detected".format(len(unique_bugs)))

        # Now group the duplicated bugs together...
        for bug_key in unique_bugs:
            pline = unfiled_bugs[bug_key]['pipeline_id']
            uf_bug = unified_bugdict[pline][bug_key]
            # Prob won't need these now:
            if 'additional info' in uf_bug:
                if 'text' in uf_bug['additional info']:
                    del uf_bug['additional info']['text']
            grouped_bugs[bug_key] = uf_bug
            grouped_bugs[bug_key]['duplicates'] = \
                [unfiled_bugs[dup]['pipeline_id'] for dup in
                 duplicates[bug_key]]
            grouped_bugs[bug_key]['match text'] = unique_bugs[bug_key]

        return (grouped_bugs, all_scores)

    def report_top_ten_bugs(self, job_names, bug_rankings,
                            url='https://bugs.launchpad.net/oil/+bug/{}'):
        """
            Print the top ten bugs for each job to the console.

            TODO: put the default url in the conf file.

        """
        for job in job_names:
            print
            print("Top bugs for job: {}".format(job))
            print("-----------------------------------")
            print
            job_ranking = bug_rankings.get(job)
            if job_ranking:
                for count, bug in enumerate(job_ranking):
                    if count < 10:
                        msg = "{0} - {1} pipelines hit"
                        if 'unfiled' not in bug[0]:
                            bug_tuple = (url.format(bug[0]), bug[1],)
                        else:
                            bug_tuple = bug
                        print(msg.format(*bug_tuple))
            else:
                print("No bugs found.")
            print

    def write_to_tmp_file(self, bug, bug_output):
        self.write_output_yaml(self.tmpdir, '{}.yml'.format(bug), bug_output,
                               False)


def main():
    refined = Refinery()
    return refined.message


if __name__ == "__main__":
    sys.exit(main())
