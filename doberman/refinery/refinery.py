#! /usr/bin/env python2

import sys
import os
import yaml
import operator
import re
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
        self.cli = CLI()
        self.all_build_numbers = []

        # Download and analyse the crude output yamls:
        self.analyse_crude_output()

        # Tidy Up:
        if not self.cli.keep_data:
            self.remove_dirs(self.all_build_numbers)

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
        self.unified_bugdict, self.job_specific_bugs_dict = \
            self.unify_downloaded_triage_files(self.cli.crude_job, marker)

        # Analyse the downloaded crude output yamls:
        self.grouped_bugs, self.all_scores = \
            self.group_similar_unfiled_bugs(self.unified_bugdict)
        self.pipelines_affected_by_bug, self.bug_rankings = \
            self.calculate_bug_prevalence(self.grouped_bugs,
                                          self.unified_bugdict,
                                          self.job_specific_bugs_dict)
        self.report_top_ten_bugs(self.bug_rankings)

        self.generate_yamls()

        try:
            self.plot = Plotting(self.bug_rankings, self.cli,
                                 self.unified_bugdict)
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

    def generate_yamls(self):
        """ Write data to output yaml files.
        """

        self.write_output_yaml(self.cli.reportdir,
                               'pipelines_affected_by_bug.yml',
                               self.pipelines_affected_by_bug)

        self.write_output_yaml(self.cli.reportdir,
                               'auto-triaged_unfiled_bugs.yml',
                               {'pipelines': self.grouped_bugs})

        for job in self.bug_rankings:
            bug_rank = self.bug_rankings[job]
            self.write_output_yaml(self.cli.reportdir,
                                   job + '_bug_ranking.yml',
                                   {'pipelines': bug_rank})

    def download_specific_file(self, job, pipeline_id, build_num, marker,
                               outdir, rename=False):
        """ Download a particular artifact from jenkins. """

        jenkins_job = self.jenkins.jenkins_api[job]
        build = jenkins_job.get_build(int(build_num))
        artifact_found = False

        if build._data['duration'] == 0:
            self.cli.LOG.info("Output unavailable (still running)")
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

    def unify_downloaded_triage_files(self, crude_job, marker):
        """
        Unify the downloaded crude output yamls into a single dictionary.

        """

        bug_dict = {}
        job_specific_bugs_dict = {}
        crude_folder = os.path.join(self.cli.reportdir, crude_job)
        if not os.path.exists(self.cli.reportdir):
            self.cli.LOG.error("{0} doesn't exist!".format(crude_folder))
        else:
            other_jobs = [j for j in self.cli.job_names if j != crude_job]
            for job in other_jobs:
                skip = False
                filename = "{0}_{1}.yml".format(marker, job)
                scan_sub_folder = False

                if os.path.exists(crude_folder):
                    if filename in os.listdir(crude_folder):
                        # If they're in the top level directory, just do this:
                        new_bugs = self.unify(crude_job, marker, job, filename,
                                              crude_folder)

                        bug_dict = self.join_dicts(bug_dict, new_bugs)

                        job_specific_bugs_dict[job] = new_bugs
                    else:
                        scan_sub_folder = True
                elif filename in os.listdir(self.cli.reportdir):
                    # If they're in the top level directory, just do this...:
                    new_bugs = self.unify(crude_job, marker, job, filename,
                                          self.cli.reportdir)

                    bug_dict = self.join_dicts(bug_dict, new_bugs)

                    job_specific_bugs_dict[job] = new_bugs
                else:
                    skip = True
                    self.cli.LOG.error("Cannot find {} in {} - skipping"
                                       .format(filename, self.cli.reportdir))

                if scan_sub_folder:
                    # ...otherwise, scan the sub-folders:
                    job_specific_bugs = {}
                    crude_dir = os.path.join(self.cli.reportdir, crude_job)

                    for build_num in os.walk(crude_folder).next()[1]:
                        new_bugs = self.unify(crude_job, marker, job, filename,
                                              crude_dir, build_num)
                        bug_dict = self.join_dicts(bug_dict, new_bugs)
                        job_specific_bugs = self.join_dicts(job_specific_bugs,
                                                            new_bugs)
                    if 'new_bugs' in locals():
                        job_specific_bugs_dict[job] = new_bugs
                if not skip:
                    self.cli.LOG.info("{} data unified.".format(job))
        return (bug_dict, job_specific_bugs_dict)

    def unify(self, crude_job, marker, job, filename, rdir, build_num=None):
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
                        if not os.path.isfile(os.path.join(op_dir, rename)):
                            params = (job, pipeline_id, build, 'console.txt',
                                      op_dir, rename)
                            try:
                                self.download_specific_file(*params)
                            except Exception, e:
                                err = "Problem fetching console data for "
                                err += "pl {} (bug {}). {}"
                                self.cli.LOG.info(err.format(pipeline_id, bug,
                                                  e))
                                bug_output['console'] = None
                        try:
                            openme = os.path.join(op_dir, rename)
                            with open(openme, 'r') as f:
                                bug_output['console'] = f.read()
                        except Exception, e:
                            err = "Could not open {} for pl {} (bug {}). {}"
                            self.cli.LOG.info(err.format(openme, pipeline_id,
                                              bug, e))
                            bug_output['console'] = None
                    bug_dict[pipeline_id][bug] = bug_output
                    # TODO: end of would be else block
        return bug_dict

    def calculate_bug_prevalence(self, unique_unfiled_bugs, unified_bugdict,
                                 job_specific_bugs_dict):
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

        for pipeline in unified_bugdict:
            for bug_no in unified_bugdict[pipeline]:
                if 'unfiled' not in bug_no:
                    job = unified_bugdict[pipeline][bug_no]['job']
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

        bug_rankings = {}
        for job_or_all in bug_prevalence:
            try:
                bug_rank = sorted(bug_prevalence[job_or_all].items(),
                                  key=operator.itemgetter(1))
                bug_rank.reverse()
            except:
                pass
            bug_rankings[job_or_all] = bug_rank

        return (pipelines_affected_by_bug, bug_rankings)

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
        if not info:
            info = bugs[bug_id].get('console')

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

    def group_similar_unfiled_bugs(self, unified_bugdict,
                                   max_sequence_size=10000):
        """
            Group unfiled bugs together by similarity of error message. If the
            string to compare is larger than the given max_sequence_size
            (default: 10000 characters) then a md5 hashlib is used to check for
            an exact match, otherwise, SequenceMatcher is used to determine if
            an error is close enough (i.e. greater than the given threshold
            value) to be considered a match.
        """

        self.cli.LOG.info("Grouping unfiled bugs by error similarity.")
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
            self.cli.LOG.info("No unfiled bugs found!")
            return (grouped_bugs, all_scores)

        unaccounted_bugs = unfiled_bugs.keys()

        ujob = unfiled_bugs[unaccounted_bugs[0]].get('job')

        if ujob in self.cli.multi_bugs_in_pl:
            multiple_bugs_per_pipeline = True
        else:
            multiple_bugs_per_pipeline = False

        report_at = self.calc_when_to_report(unaccounted_bugs)

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
            progress = [round((pc / 100.0) * len(unaccounted_bugs)) for pc in
                        report_at]
            if pos in progress:
                pc = str(report_at[progress.index(pos)])
                self.cli.LOG.info("Bug grouping {0}% complete.".format(pc))

        self.cli.LOG.info("{} unique bugs detected".format(len(unique_bugs)))

        # Now group the duplicated bugs together...
        for bug_key in unique_bugs:
            pline = unfiled_bugs[bug_key]['pipeline_id']
            uf_bug = unified_bugdict[pline][bug_key]
            # Prob won't need these now:
            if 'additional info' in uf_bug:
                if 'text' in uf_bug['additional info']:
                    del uf_bug['additional info']['text']
            if 'console' in uf_bug:
                del uf_bug['console']
            grouped_bugs[bug_key] = uf_bug
            grouped_bugs[bug_key]['duplicates'] = \
                [unfiled_bugs[dup]['pipeline_id'] for dup in
                 duplicates[bug_key]]
            grouped_bugs[bug_key]['match text'] = unique_bugs[bug_key]

        return (grouped_bugs, all_scores)

    def report_top_ten_bugs(self, bug_rankings):
        """ Print the top ten bugs for each job to the console. """
        for job in self.cli.job_names:
            if job != self.cli.crude_job:
                print
                print("Top bugs for job: {}".format(job))
                print("-----------------------------------")
                print
                if bug_rankings.get(job):
                    for count, bug in enumerate(bug_rankings.get(job)):
                        if count < 10:
                            msg = "{0} - {1} duplicates"
                            print(msg.format(bug[0], bug[1]))
                else:
                    print("No bugs found.")
                print


def main():
    refined = Refinery()
    return refined.message


if __name__ == "__main__":
    sys.exit(main())
