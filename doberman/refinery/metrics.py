#! /usr/bin/env python2

import sys
import os
import yaml
import operator
import re
import matplotlib.pyplot as plt
from jenkinsapi.custom_exceptions import *
from doberman.analysis.analysis import CrudeAnalysis, CLI
from doberman.analysis.crude_jenkins import Jenkins
from doberman.analysis.crude_test_catalog import TestCatalog
from difflib import SequenceMatcher
from pylab import xticks, yticks, gca, title
from matplotlib.backends.backend_pdf import PdfPages


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

        self.debug = False
        self.message = -1
        self.cli = CLI()

        # Download and analyse the crude output yamls:
        self.analyse_crude_output()

        # Tidy Up:
        if not self.debug:
            self.remove_dirs(self.all_build_numbers)

    def analyse_crude_output(self):
        """ Get and analyse the crude output yamls.
        """
        # Get crude output:
        marker = 'triage'
        self.jenkins = Jenkins(self.cli)
        if not self.debug:
            self.test_catalog = TestCatalog(self.cli)
            self.build_pl_ids_and_check()
            output_folder = self.cli.reportdir
            self.download_triage_files(self.cli.crude_job, marker,
                                       output_folder)
        else:
            self.cli.LOG.info("*** Debugging mode is on. ***")
        self.unified_bugs_dict = self.unify_downloaded_triage_files(
            self.cli.crude_job, marker)

        # Analyse the downloaded crude output yamls:
        self.group_similar_unfiled_bugs(self.unified_bugs_dict)
        self.pipelines_affected_by_bug = self.calculate_bug_prevalence(
            self.grouped_bugs, self.unified_bugs_dict)

        self.write_output_yaml(self.cli.reportdir,
                               'auto-triaged_unfiled_bugs.yml',
                               {'pipelines': self.grouped_bugs})
        self.write_output_yaml(self.cli.reportdir,
                               'bug_ranking.yml',
                               {'pipelines': self.bug_rank})
        self.plot(self.bug_rank, self.cli.reportdir, 'charts.pdf')

    def download_specific_file(self, job, pipeline_id, build_num, marker,
                               outdir, rename=False):
        """ Download a particular artifact from jenkins. """

        if not self.debug:
            jenkins_job = self.jenkins.jenkins_api[job]
            build = jenkins_job.get_build(int(build_num))

            if build._data['duration'] == 0:
                self.cli.LOG.info("Output unavailable (still running)")
                return
            try:
                os.makedirs(outdir)
            except OSError:
                if not os.path.isdir(outdir):
                    raise

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
        for pipeline_id in self.pipeline_ids:
            try:
                build_numbers = self.test_catalog.get_pipelines(pipeline_id)
                build_num = build_numbers.get(job)
                outdir = os.path.join(output_folder, str(build_num))
                if build_num:
                    self.all_build_numbers.append(build_num)
                    self.download_specific_file(job, pipeline_id,
                                                build_num, marker, outdir)
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
        other_jobs = [j for j in self.cli.job_names if j != crude_job]
        bug_dict = {}
        for job in other_jobs:
            for build_num in os.walk(self.cli.reportdir).next()[1]:
                # TODO: or for build_num in self.all_build_numbers ???
                filename = "{0}_{1}.yml".format(marker, job)
                file_location = os.path.join(self.cli.reportdir, build_num,
                                             filename)

                # Now read in each yaml output file:
                try:
                    with open(file_location, "r") as f:
                        yaml_content = yaml.load(f)
                        output = yaml_content.get('pipeline')
                except:
                    output = None

                # Combine all yamls by pipeline:
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

                            plop = output[pipeline_id]  # This is Ryan's fault!
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
                            try:
                                if 'unfiled' in bug:
                                    op_dir = os.path.join(self.cli.reportdir,
                                                          build_num)
                                    rename = "{0}_console.txt".format(job)
                                    params = (job, pipeline_id, build,
                                              'console.txt', op_dir, rename)
                                    self.download_specific_file(*params)
                                    path = os.path.join(op_dir, rename)
                                    with open(path, 'r') as f:
                                        bug_output['console'] = f.read()

                            except Exception, e:
                                err = "Problem fetching console data for "
                                err += "pl {0} (bug {1}). {2}"
                                err = err.format(pipeline_id, bug, e)
                                self.cli.LOG.info(err)
                                bug_output['console'] = None
                            bug_dict[pipeline_id][bug] = bug_output
                            # TODO: end of would be else block
        return bug_dict

    def calculate_bug_prevalence(self, unique_unfiled_bugs, unified_bugs_dict):
        """
        calculate_bug_prevalence
        Needs to make charts too...
        """
        self.cli.LOG.info("Analysing the downloaded crude output yamls.")
        bug_prevalence = {}
        pipelines_affected_by_bug = {}
        for bug_no in unique_unfiled_bugs:
            bug_prevalence[bug_no] = len(unique_unfiled_bugs[bug_no]
                                         ['duplicates'])
            pipelines_affected_by_bug[bug_no] = \
                unique_unfiled_bugs[bug_no]['duplicates']

        for pipeline in unified_bugs_dict:
            for bug_no in unified_bugs_dict[pipeline]:
                if 'unfiled' not in bug_no:
                    if bug_no not in bug_prevalence:
                        bug_prevalence[bug_no] = 1
                    else:
                        bug_prevalence[bug_no] = bug_prevalence[bug_no] + 1
                    if bug_no not in pipelines_affected_by_bug:
                        pipelines_affected_by_bug[bug_no] = []
                    pipelines_affected_by_bug[bug_no].append(pipeline)

        # Print out to user the bug ranking:
        bug_rank = sorted(bug_prevalence.items(), key=operator.itemgetter(1))
        bug_rank.reverse()
        self.bug_rank = bug_rank

        return pipelines_affected_by_bug

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
        traceback = " ".join([str(n) for n in traceback_list])

        # Search for errors:
        errs = sorted(re.findall('ERROR.*', info))

        # Search for failure:
        fails = sorted(re.findall('fail.*', info, re.IGNORECASE))
        bug_feedback = " ".join([str(n) for n in (traceback, errs, fails)])
        if bug_feedback == ' [] []':
            return None
        else:
            return bug_feedback

    def group_similar_unfiled_bugs(self, unified_bugs_dict):
        """

        """
        self.cli.LOG.info("Grouping similar unfiled bugs by error similarity.")
        unfiled_bugs = {}
        for pipeline in unified_bugs_dict:
            for bug_no in unified_bugs_dict[pipeline]:
                if 'unfiled' in bug_no:
                    unfiled_bugs[bug_no] = unified_bugs_dict[pipeline][bug_no]

        duplicates = {}
        unaccounted_bugs = unfiled_bugs.keys()
        all_scores = []
        for unf_bug_a in unaccounted_bugs:
            duplicates[unf_bug_a] = [unf_bug_a]
            try:
                info_a = self.normalise_bug_details(unfiled_bugs, unf_bug_a)
            except:
                continue
            for unf_bug_b in unaccounted_bugs:
                if unf_bug_b != unf_bug_a:
                    try:
                        info_b = self.normalise_bug_details(unfiled_bugs,
                                                            unf_bug_b)
                        score = SequenceMatcher(None, info_a,
                                                info_b).ratio()
                        all_scores.append(score)
                    except:
                        score = -1
                    if score > self.cli.match_threshold:
                        if unf_bug_b not in duplicates:
                            try:
                                unaccounted_bugs.remove(unf_bug_a)
                            except:
                                pass
                            duplicates[unf_bug_a].append(unf_bug_b)
                            try:
                                unaccounted_bugs.remove(unf_bug_b)
                            except:
                                pass

        # Now group the duplicated bugs together...
        grouped_bugs = {}
        for bug_key in duplicates:
            pline = unfiled_bugs[bug_key]['pipeline_id']
            uf_bug = unified_bugs_dict[pline][bug_key]
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

        # ...and not forgetting any unique bugs:
        for bug_key in unaccounted_bugs:
            pline = unfiled_bugs[bug_key]['pipeline_id']
            uf_bug = unified_bugs_dict[pline][bug_key]
            # Prob won't need these now:
            if 'additional info' in uf_bug:
                if 'text' in uf_bug['additional info']:
                    del uf_bug['additional info']['text']
            if 'console' in uf_bug:
                del uf_bug['console']
            grouped_bugs[bug_key] = uf_bug
            grouped_bugs[bug_key] = unified_bugs_dict[pline][bug_key]
            grouped_bugs[bug_key]['duplicates'] = [pline]

        self.grouped_bugs = grouped_bugs
        self.all_scores = all_scores

    def plot(self, bugs, reportdir, filename):
        pdf_path = os.path.join(reportdir, filename)
        bug_ids = [bug[0] for bug in bugs]
        totals = [int(bug[1]) for bug in bugs]
        pdf = PdfPages(pdf_path)
        self.plot_bar(bug_ids, totals, pdf)
        self.plot_pie(bug_ids, totals, pdf)
        pdf.close()

    def plot_bar(self, bug_ids, totals, pdf):
        fig = plt.figure()
        # The slices will be ordered and plotted counter-clockwise.
        # colors = ['yellowgreen', 'gold', 'lightskyblue', 'lightcoral']
        # explode = (0, 0.1, 0, 0) # only "explode" the 2nd slice (i.e. 'Hogs')
        # plt.pie(totals, explode=explode, labels=bug_ids, colors=colors,
        plt.pie(totals, labels=bug_ids, autopct='%1.1f%%', shadow=True,
                startangle=90)
        # Set aspect ratio to be equal so that pie is drawn as a circle.
        plt.axis('equal')
        pdf.savefig(fig)

    def plot_pie(self, bug_ids, totals, pdf):
        fig = plt.figure()
        width = 0.5
        xloc = [x + width for x in range(0, len(bug_ids), 1)]
        plt.bar(xloc, totals, width=width)
        xticks(xloc, bug_ids)
        title("Bug Ranking")
        gca().get_xaxis().tick_bottom()
        gca().get_yaxis().tick_left()
        pdf.savefig(fig)


def main():
    refined = Refinery()
    return refined.message


if __name__ == "__main__":
    sys.exit(main())
