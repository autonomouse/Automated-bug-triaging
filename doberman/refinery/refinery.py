#! /usr/bin/env python2

import sys
import os
import yaml
import operator
import re
from jenkinsapi.custom_exceptions import *
from doberman.analysis.analysis import CrudeAnalysis
from doberman.analysis.crude_jenkins import Jenkins
from doberman.analysis.crude_test_catalog import TestCatalog
from plotting import Plotting
from difflib import SequenceMatcher
from cli import CLI
from collections import deque


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
        if not self.cli.offline_mode:
            self.jenkins = Jenkins(self.cli)
            self.test_catalog = TestCatalog(self.cli)
            self.build_pl_ids_and_check()
            self.download_triage_files(self.cli.crude_job, marker,
                                       self.cli.reportdir)
        else:
            self.cli.LOG.info("*** Offline mode is on. ***")
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

        self.plot = Plotting(self.bug_rankings, self.cli,
                             self.unified_bugdict)

        if 'pipeline_ids' in self.__dict__:
            self.log_pipelines()

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

        self.all_build_numbers = []
        build_numbers = self.test_catalog.get_all_pipelines(self.pipeline_ids)

        for pipeline_id in self.pipeline_ids:
            try:
                build_num = build_numbers[pipeline_id].get(job)

                if build_num:
                    outdir = os.path.join(output_folder, str(build_num))
                    self.all_build_numbers.append(build_num)
                    self.download_specific_file(job, pipeline_id, build_num,
                                                marker, outdir)
                else:
                    self.cli.LOG.info("No build number found: job {0} for {1}"
                                      .format(job, pipeline_id))
            except Exception, e:
                self.cli.LOG.error("Error downloading pipeline {0} ({1}) - {2}"
                                   .format(job, pipeline_id, e))

    def unify_downloaded_triage_files(self, crude_job, marker):
        """
        Unify the downloaded crude output yamls into a single dictionary.

        """

        bug_dict = {}
        job_specific_bugs_dict = {}
        if not os.path.exists(self.cli.reportdir):
            self.cli.LOG.error("{0} doesn't exist!"
                               .format(self.cli.reportdir))
        else:
            other_jobs = [j for j in self.cli.job_names if j != crude_job]
            for job in other_jobs:
                filename = "{0}_{1}.yml".format(marker, job)
                if filename in os.listdir(self.cli.reportdir):
                    # If they're in the top level directory, just do this...:
                    new_bugs = self.unify(crude_job, marker, job, filename)

                    bug_dict = self.join_dicts(bug_dict, new_bugs)

                    job_specific_bugs_dict[job] = new_bugs
                else:
                    # ...otherwise, scan the sub-folders:
                    job_specific_bugs = {}
                    for build_num in os.walk(self.cli.reportdir).next()[1]:
                        new_bugs = self.unify(crude_job, marker, job, filename,
                                              build_num)
                        bug_dict = self.join_dicts(bug_dict, new_bugs)
                        job_specific_bugs = self.join_dicts(job_specific_bugs,
                                                            new_bugs)
                    if 'new_bugs' in locals():
                        job_specific_bugs_dict[job] = new_bugs
        return (bug_dict, job_specific_bugs_dict)

    def unify(self, crude_job, marker, job, filename, build_num=None):
        """
        Unify the downloaded crude output yamls into a single dictionary.

        """

        if build_num:
            file_location = os.path.join(self.cli.reportdir, build_num,
                                         filename)
        else:
            file_location = os.path.join(self.cli.reportdir, filename)
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
                        op_dir = os.path.join(self.cli.reportdir, job, 
                                              build_num)
                        #rename = "{0}_console.txt".format(job)
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
                        with open(os.path.join(op_dir, rename), 'r') as f:
                            bug_output['console'] = f.read()
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
            return self.get_xunit_class_and_name(bugs, bug_id)
        else:            
            return self.normalise_bug_details(bugs, bug_id)
    
    def get_xunit_class_and_name(self, bugs, bug_id):
        """ Make info_a/b equal to xunitclass + xunitname. """
        try:
            addinfo = bugs[bug_id].get('additional info')
            return "{} {}".format(addinfo['xunit class'], addinfo['xunit name'])
        except:
            return None 

    def normalise_bug_details(self, bugs, bug_id):
        """
        get info on bug from additional info. Replace build number,
        pipeline id, date newlines, \ etc with blanks...
        """
        bug = bugs[bug_id]
        info = bug.get('console')

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

    def group_similar_unfiled_bugs(self, unified_bugdict, maxlen=5):
        """
        Group unfiled bugs together by similarity of error message. This
        whole section is currently a little silly and needs replacing by an
        fminsearch style ODE-solver thing, to minimise the length of
        unaccounted bugs.
        """
        self.cli.LOG.info("Grouping similar unfiled bugs by error similarity.")
        unfiled_bugs = {}
        for pipeline in unified_bugdict:
            for bug_no in unified_bugdict[pipeline]:
                if 'unfiled' in bug_no:
                    unfiled_bugs[bug_no] = unified_bugdict[pipeline][bug_no]

        duplicates = {}
        text = {}
        unaccounted_bugs = unfiled_bugs.keys()
        all_scores = {}

        bah_numbugs = deque(maxlen=maxlen)
        while len(unaccounted_bugs) > 1:
            self.cli.LOG.info("{} unaccounted bugs remaining..."
                              .format(len(unaccounted_bugs)))
            unaccounted_bugs, duplicates, text, all_scores = self.loop_group(
                unfiled_bugs, unaccounted_bugs, duplicates, text, all_scores)
            bah_numbugs.append(len(unaccounted_bugs))
            if len(bah_numbugs) == maxlen:
                # If the number of unfiled bugs has not reduced in maxlen
                # number of attempts, then break:
                if not (bah_numbugs[-1] < bah_numbugs[0]):
                    break

        # Mop up the last one(s), if necessary:
        if len(unaccounted_bugs):
            msg = "The remaining {} unaccounted bug(s) appear to be unique "
            msg += "(match threshold of {})"
        else:
            msg = "All bugs accounted for (match threshold of {1})"
        thshld = self.cli.match_threshold
        self.cli.LOG.info(msg.format(len(unaccounted_bugs), thshld))
        for unf_bug in unaccounted_bugs:
            duplicates[unf_bug] = [unf_bug]
            info_a = self.normalise_bug_details(unfiled_bugs, unf_bug)
            text[unf_bug] = info_a
            unaccounted_bugs.remove(unf_bug)
        '''
        # Re-compare only those bugs identified as having duplicates (to
        # quickly check that the list cannot be further reduced):
        self.cli.LOG.info("Double checking...")
        unaccounted_bugs = duplicates.keys()
        new_unaccounted_bugs, new_duplicates, new_text, new_all_scores = \
            self.loop_group(unfiled_bugs, unaccounted_bugs, {}, text,
                            all_scores)
        # For any new_duplicates with more than one duplicate, copy in the
        # duplicates's duplicates (sorry!) into one and remove the others:
        for dupe in new_duplicates:
            if len(new_duplicates[dupe]) > 1:
                for double_dupe in new_duplicates[dupe]:
                    if double_dupe != dupe:
                        duplicates[dupe].extend(duplicates[double_dupe])
                        del duplicates[double_dupe]
            duplicates[dupe] = set(duplicates[dupe])
        '''
        
        if len(duplicates):
            num_dupes = len(duplicates)
            self.cli.LOG.info("{} unique bugs detected".format(num_dupes))

        # Now group the duplicated bugs together...
        grouped_bugs = {}
        for bug_key in duplicates:
            pline = unfiled_bugs[bug_key]['pipeline_id']
            uf_bug = unified_bugdict[pline][bug_key]
            # Prob won't need these now:
            if 'additional info' in uf_bug:
                if 'text' in uf_bug['additional info']:
                    if 'text' in uf_bug['additional info']:
                        del uf_bug['additional info']['text']
            if 'console' in uf_bug:
                del uf_bug['console']
            grouped_bugs[bug_key] = uf_bug
            grouped_bugs[bug_key]['duplicates'] = \
                [unfiled_bugs[dup]['pipeline_id'] for dup in
                 duplicates[bug_key]]
            grouped_bugs[bug_key]['match text'] = text.get(bug_key)

        return (grouped_bugs, all_scores)
                    
    def loop_group(self, unfiled_bugs, unaccounted_bugs, duplicates, text,
                   all_scores):
        """
        """
        unaccounted = list(unaccounted_bugs)  # copies list, not just link to it
        if unfiled_bugs[unaccounted[0]].get('job') in self.cli.multi_bugs_in_pl:
            multiple_bugs_per_pipeline = True
        else:
            multiple_bugs_per_pipeline = False            
        
        for unf_bug_a in unaccounted:
            duplicates[unf_bug_a] = [unf_bug_a]
            info_a = self.get_identifying_bug_details(
                unfiled_bugs, unf_bug_a, multiple_bugs_per_pipeline)
            text[unf_bug_a] = info_a
            for unf_bug_b in unaccounted:
                if unf_bug_b != unf_bug_a:
                    info_b = self.get_identifying_bug_details(
                        unfiled_bugs, unf_bug_b, multiple_bugs_per_pipeline)
                    try:            
                        score = SequenceMatcher(None, string1, string2).ratio()
                    except:
                        score = -1
                    if multiple_bugs_per_pipeline:
                        threshold = 1.0
                    else:
                        threshold = float(self.cli.match_threshold)                    
                    if score >= threshold:
                        if unf_bug_a not in all_scores:
                            all_scores[unf_bug_a] = {}
                        all_scores[unf_bug_a][unf_bug_b] = score
                        if unf_bug_b not in duplicates:
                            try:
                                unaccounted.remove(unf_bug_a)
                            except:
                                pass
                            duplicates[unf_bug_a].append(unf_bug_b)
                            try:
                                unaccounted.remove(unf_bug_b)
                            except:
                                pass
        return (unaccounted, duplicates, text, all_scores)           
                        
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
                            print("{0} - {1} duplicates".format(bug[0], bug[1]))
                else:
                    print("No bugs found.")
                print


def main():
    refined = Refinery()
    return refined.message


if __name__ == "__main__":
    sys.exit(main())
