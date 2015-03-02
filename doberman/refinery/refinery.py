#! /usr/bin/env python2

import sys
import os
import yaml
import operator
import re
import shutil
import tempfile
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
        self.bug_rankings = {}
        self.console_output = {}
        self.info_file_cache = {}
        self.max_sequence_size = 10000  # <- Put this in doberman.conf

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
        other_jobs = [j for j in self.cli.job_names if j != self.cli.crude_job]

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
            self.cli.op_dir_structure = \
                self.determine_folder_structure(other_jobs)
        self.cli.LOG.info("Working on {0} as refinery input directory"
                          .format(self.cli.reportdir))
        self.unified_bugdict, self.job_specific_bugs_dict = \
            self.unify_downloaded_triage_files(self.cli.crude_job, marker,
                                               other_jobs)

        # Analyse the downloaded crude output yamls:
        self.grouped_bugs, self.all_scores = \
            self.group_similar_unfiled_bugs(self.unified_bugdict)
        self.pipelines_affected_by_bug, self.bug_rankings = \
            self.calculate_bug_prevalence(self.grouped_bugs,
                                          self.unified_bugdict,
                                          self.job_specific_bugs_dict)

        self.report_top_ten_bugs(other_jobs, self.bug_rankings)
        if 'pipeline_ids' in self.__dict__:
            self.log_pipelines()
        self.generate_yamls()

        try:
            self.plot = Plotting(self.cli)
        except:
            self.cli.LOG.info("Unable to generate plots.")

    def determine_folder_structure(self, jobs):
        """
            Set directory structure for downloads, where 0 is reportdir, 1 is
            job name and 2 is build number.
        """
        crude_folder = os.path.join(self.cli.reportdir, self.cli.crude_job)

        if not os.path.exists(self.cli.reportdir):
            emsg = "Directory doesn't exist! {}".format(self.cli.reportdir)
            self.cli.LOG.error(emsg)
            raise Exception(emsg)
        else:
            for job in jobs:
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
            bug_rank = self.bug_rankings.get(job)
            fn = 'bug_ranking_{}.yml'.format(job)
            self.write_output_yaml(self.cli.reportdir, fn, bug_rank)

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
                self.cli.LOG.debug("{0} file saved to {1} as {2}"
                                   .format(marker, outdir, rn_to))
            else:
                self.cli.LOG.debug("{0} file saved to {1}"
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

    def move_artifacts_from_crude_job_folder(self, marker, jobs):
        """ """

        crude_job = self.cli.crude_job

        if crude_job in os.walk(self.cli.reportdir).next()[1]:
            path_to_crude_folder = os.path.join(self.cli.reportdir, crude_job)
            for build_num in os.walk(path_to_crude_folder).next()[1]:
                bpath = os.path.join(path_to_crude_folder, build_num)
                pipelines = [x for x in self.build_numbers if
                             self.build_numbers[x].get(crude_job) == build_num]
                pipeline = pipelines[0]  # There can be only one...
                for job in jobs:
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

    def unify_downloaded_triage_files(self, crude_job, marker, jobs):
        """
        Unify the downloaded crude output yamls into a single dictionary.

        """

        bug_dict = {}
        job_specific_bugs_dict = {}
        crude_folder = os.path.join(self.cli.reportdir, crude_job)
        if not os.path.exists(self.cli.reportdir):
            self.cli.LOG.error("{0} doesn't exist!".format(crude_folder))
        else:
            for job in jobs:
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
            for pos, pipeline_id in enumerate(output):
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
                        rename = "{}_console.txt".format(job)

                        # If a bug is unfiled, it should provide the console as
                        # default:
                        if bug_output['additional info'].get('target file') !=\
                                'console.txt':
                            bug_output['additional info']['target file'] = \
                                'console.txt'

                        # Check to see if console is present. If not, download:
                        a_file = os.path.join(op_dir, rename)
                        if not os.path.isfile(a_file):
                            params = (job, pipeline_id, build, 'console.txt',
                                      op_dir, rename)
                        try:
                            # Check to see if the file is there already first
                            # rename:
                            if not (os.path.isfile(os.path.join(op_dir,
                                    rename))):
                                self.download_specific_file(*params)
                        except Exception, e:
                            err = "Problem fetching console data for "
                            err += "pl {} (bug {}). {}"
                            self.cli.LOG.info(err.format(pipeline_id, bug, e))
                            bug_output['additional info']['text'] = None

                        openme = os.path.join(op_dir, rename)
                        try:
                            bug_output['additional info']['text'] = openme
                        except Exception, e:
                            err = "Could not open {} for pl {} (bug {}). {}"
                            self.cli.LOG.info(err.format(openme, pipeline_id,
                                              bug, e))
                            bug_output['additional info']['text'] = None
                    bug_dict[pipeline_id][bug] = bug_output
                    # TODO: end of would be else block

                # Notify user of progress:
                pl_prgrs = self.calculate_progress(pos, output)
                if pl_prgrs:
                    self.cli.LOG.info("Unification of {} data {}% complete."
                                      .format(pl_prgrs, job))
        return bug_dict

    def calculate_bug_prevalence(self, unique_unfiled_bugs, unified_bugdict,
                                 job_specific_bugs_dict):
        """
            Calculate_bug_prevalence
        """
        self.cli.LOG.info("Analysing the downloaded crude output yamls.")
        bug_prevalence = {'all_bugs': {}}
        pipelines_affected_by_bug = {}

        for pipeline in unique_unfiled_bugs:
            for bug_no in unique_unfiled_bugs[pipeline]:
                job = unique_unfiled_bugs[pipeline][bug_no]['job']
                if job not in bug_prevalence:
                    bug_prevalence[job] = {}
                if 'all_bugs' not in bug_prevalence:
                    bug_prevalence['all_bugs'] = {}
                dupes = unique_unfiled_bugs[pipeline][bug_no]['duplicates']
                bug_prevalence[job][bug_no] = len(dupes)
                bug_prevalence['all_bugs'][bug_no] = len(dupes)
                pipelines_affected_by_bug[bug_no] = dupes

        for pipeline in unified_bugdict:
            for bug_no in unified_bugdict[pipeline]:
                if 'unfiled' not in bug_no:
                    job = unified_bugdict[pipeline][bug_no]['job']
                    if job not in bug_prevalence:
                        bug_prevalence[job] = {}
                    if 'filed_bugs_only' not in bug_prevalence:
                        bug_prevalence['filed_bugs_only'] = {}
                    if bug_no not in bug_prevalence[job]:
                        bug_prevalence['filed_bugs_only'][bug_no] = 1
                        bug_prevalence[job][bug_no] = 1
                    else:
                        bug_prevalence['filed_bugs_only'][bug_no] = \
                            bug_prevalence['filed_bugs_only'][bug_no] + 1
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
            Get info on bug from additional info. Replace build number,
            pipeline id, date newlines, \ etc with blanks...
        """
        pipelines = [bugs[b].get('pipeline_id') for b in bugs]

        # Temporarily load up the whole output file into memory:
        if not info:
            if 'additional info' in bugs[bug_id]:
                info_file = bugs[bug_id]['additional info'].get('text')
            else:
                msg = "No console data or info provided for bug id: {}."
                self.cli.LOG.debug(msg.format(bug_id))
                return
        
        if self.info_file_cache.has_key(info_file):    
            return self.info_file_cache[info_file]
            
        # No reason to read and normalize this big files that won't
        # go through sequence matching anyhow. 
        stat_result = os.stat(info_file)
        if stat_result.st_size > self.max_sequence_size:
            self.info_file_cache[info_file] = None
            return
        
        with open(info_file, 'r') as f:
            info = f.read()
            
        # replace pipeline id(s) with placeholder:
        pl_placeholder = 'AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'
        for pl in pipelines:
            info = info.replace(pl, pl_placeholder) if info else ''

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
            self.info_file_cache[info_file] = None
            return
        else:
            self.info_file_cache[info_file] = bug_feedback
            return bug_feedback

    def group_similar_unfiled_bugs(self, unified_bugdict):
        """
            Group unfiled bugs together by similarity of error message. If the
            string to compare is larger than the given max_sequence_size
            (default: 10000 characters), this strings are compared for an
            exact match, otherwise, SequenceMatcher is used to determine if
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

        for pos, unfiled_bug in enumerate(unaccounted_bugs):
            info_a = \
                self.get_identifying_bug_details(unfiled_bugs, unfiled_bug,
                                                 multiple_bugs_per_pipeline)

            # Have we seen this bug before?
            for already_seen in unique_bugs:
                info_b = unique_bugs[already_seen]
                if info_a and info_b:
                    if info_a == info_b:
                        score = 1
                        msg = "{} and {} are equivalent."
                        self.cli.LOG.debug(msg.format(already_seen,
                                                      unfiled_bug))
                    elif (len(info_a) + len(info_b)) > self.max_sequence_size:
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
            # Prob won't need this now:
            if 'additional info' in uf_bug:
                if 'text' in uf_bug['additional info']:
                    del uf_bug['additional info']['text']
            if pline not in grouped_bugs:
                grouped_bugs[pline] = {}
            grouped_bugs[pline][bug_key] = uf_bug
            grouped_bugs[pline][bug_key]['duplicates'] = \
                [unfiled_bugs[dup]['pipeline_id'] for dup in
                 duplicates[bug_key]]
            grouped_bugs[pline][bug_key]['match text'] = unique_bugs[bug_key]

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


def main():
    refined = Refinery()
    return refined.message


if __name__ == "__main__":
    sys.exit(main())
