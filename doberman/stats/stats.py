#! /usr/bin/env python2

import os
import sys
import yaml
import shutil
from lxml import etree
from datetime import datetime
from stats_cli import CLI
from pprint import pprint
from doberman.common.base import DobermanBase
from doberman.analysis.crude_jenkins import Jenkins
from doberman.analysis.crude_weebl import WeeblClass
from jenkinsapi.custom_exceptions import UnknownJob


class Stats(DobermanBase):

    def __init__(self, cli=False):
        self.message = 1
        stats_start_time = datetime.now()
        self.cli = CLI().populate_cli() if not cli else cli
        self.intro = ("Data for OIL Environment: {} (Jenkins host: {})"
                      .format(self.cli.environment,
                              self.cli.external_jenkins_url))
        self.cli.LOG.info(self.intro)
        self.weebl = WeeblClass(self.cli)
        self.jenkins = Jenkins(self.cli)
        self.jenkins_api = self.jenkins.jenkins_api
        self.op_dirs = []
        self.run_stats()
        stats_finish_time = datetime.now()
        self.cli.LOG.info(self.report_time_taken(
            stats_start_time, stats_finish_time))
        self.message = 0

    def run_stats(self, stats_file="stats.txt"):
        self.build_numbers = self.build_pl_ids_and_check(
            self.jenkins, self.weebl)

        # Make a list of jobs that aren't the crude job:
        self.non_crude_job_names = [job for job in self.cli.job_names if
                                    job != self.cli.crude_job]

        # Set up output dict:
        results = {'jobs': {}, 'overall': {}}
        totals = {}

        # Fetch data:
        builds, actives, bld_artifacts = self.get_builds()
        for job in self.non_crude_job_names:
            self.cli.LOG.debug("{}:".format(job))
            job_dict = self.populate_job_dict(
                job, builds, actives, bld_artifacts)
            results['jobs'][job] = job_dict
            # Calculate totals:
            totals[job] = {'total_builds': job_dict['build objects'],
                           'passing': job_dict.get('passes', 0)}

        # Calculate overall success rate
        results = self.calculate_overall_success_rates(totals, results)

        # Report results:
        fname = os.path.join(self.cli.reportdir, stats_file)
        self.write_intro_to_results_file(fname)
        for job in self.non_crude_job_names:
            # I wanted to do "for job in results.keys():" here, but then they
            # wouldn't be reported in the correct order.
            self.write_to_results_file(fname, results, job)

        # Overall success:
        if self.cli.summary:
            self.write_summary_to_results_file(fname, totals, results)

        # Save results to file:
        self.generate_output_file(results)
        self.print_results(fname)

        # Clean up:
        if not self.cli.keep_data and not self.cli.triage:
            self.tidy_up()

    def create_output_directory(self, subfolder):
        op_dir = os.path.abspath(os.path.join(
            self.cli.reportdir, subfolder))
        self.mkdir(op_dir)
        self.op_dirs.append(op_dir)
        return op_dir

    def generate_output_file(self, results):
        op_loc = os.path.join(self.cli.reportdir, "stats_results.yaml")
        with open(op_loc, "w") as output:
            output.write(yaml.safe_dump(results))
            self.cli.LOG.info("Results yaml written to {}"
                              .format(self.cli.reportdir))

    def get_builds(self):
        all_builds = {}
        builds = {}
        actives = {}
        pipelines_to_remove = []
        bld_artifacts = {}
        if self.build_numbers in [None, {}]:
            return {}, {}, None
        for job in self.non_crude_job_names:
            try:
                jenkins_job = self.jenkins_api[job]
            except UnknownJob:
                self.cli.LOG.error("{} job is not recognised.".format(job))
                continue
            self.cli.LOG.info("Polling Jenkins for {} data".format(job))
            url = jenkins_job.python_api_url(jenkins_job.baseurl)
            all_builds[job] = jenkins_job.get_data(
                url, params={'depth': 1})['builds']
            actives[job] = []
            for pipeline, build_dict in self.build_numbers.items():
                build_number = build_dict.get(job)
                if build_number is None:
                    continue

                if self.cli.triage:
                    op_dir = self.create_output_directory(job)
                    self.jenkins.get_triage_data(build_number, job, op_dir)

                try:
                    this_build = [b for b in all_builds[job] if b['number'] ==
                                  int(build_number)][0]
                except IndexError:
                    continue

                if self.is_running(this_build):
                    actives[job].append(this_build)
                    pipelines_to_remove.append(pipeline)
                    self.cli.LOG.info("{} build {} is still running"
                                      .format(job, this_build['number']))

                if job in self.cli.multi_bugs_in_pl:
                    if job not in bld_artifacts:
                        bld_artifacts[job] = {}
                    self.cli.LOG.debug("Getting artifacts for {} build {}"
                                       .format(job, this_build['number']))
                    all_artifacts = []
                    for xml in self.cli.xmls:
                        artifacts = [
                            artifact for artifact in
                            jenkins_job[this_build['number']].get_artifacts()
                            if xml in str(artifact)]

                        all_artifacts.extend(artifacts)
                    bld_artifacts[job][this_build['number']] =\
                        all_artifacts if all_artifacts else []

        for pipeline in set(pipelines_to_remove):
            self.build_numbers.pop(pipeline)

        for job in self.non_crude_job_names:
            if job not in all_builds:
                continue
            completed_builds = [
                int(bs[job]) for pl, bs in self.build_numbers.items()
                if bs.get(job) is not None]
            builds[job] = [b for b in all_builds[job] if b['number'] in
                           completed_builds]
        return builds, actives, bld_artifacts

    def get_start_idx_num_and_date(self, builds,
                                   ts_format='YYYY-MMM-DD HH:mm:ss'):
        # I could just use and index of -1 here as they're already supposed to
        # be ordered, but to be thorough:
        min_ts, start_idx = min((b.get('timestamp'), idx) for idx, b in
                                enumerate(builds))

        start_num = builds[start_idx]['number']
        start_in_ms = min_ts / 1000
        start_date = datetime.fromtimestamp(start_in_ms)
        return (start_idx, start_num, start_date)

    def get_end_idx_num_and_date(self, builds,
                                 ts_format='YYYY-MMM-DD HH:mm:ss'):
        # I could just use and index of 0 here as they're already supposed to
        # be ordered, but to be thorough:
        max_ts, end_idx = max((b.get('timestamp'), idx) for idx, b in
                              enumerate(builds))

        end_num = builds[end_idx]['number']
        end_in_ms = max_ts / 1000
        end_date = datetime.fromtimestamp(end_in_ms)
        return (end_idx, end_num, end_date)

    def populate_job_dict(self, job, all_builds, all_actives, bld_artifacts):
        job_dict = {}
        builds = all_builds.get(job)
        num_active = len(all_actives.get(job, {}))
        job_dict['still_running'] = num_active
        if builds in [None, []]:
            job_dict['build objects'] = 0 + num_active
            return job_dict

        start_idx, start_num, start_date =\
            self.get_start_idx_num_and_date(builds)
        job_dict['start job'] = start_num
        job_dict['start date'] = start_date

        end_idx, end_num, end_date = self.get_end_idx_num_and_date(builds)
        job_dict['end job'] = end_num
        job_dict['end date'] = end_date

        nr_builds = len(all_builds[job])
        job_dict['build objects'] = nr_builds + num_active
        job_dict = self.get_passes_and_fails(
            job, job_dict, builds, bld_artifacts)
        msg = "There are {} {} builds"
        if num_active != 0:
            msg += " (ignoring the {} builds that are still active)"
        self.cli.LOG.info(msg.format(nr_builds, job, num_active))
        return job_dict

    def get_passes_and_fails(self, job, job_dict, build_objs, bld_artifacts):

        # TODO: handle case where we don't have active, good or bad builds
        good = filter(lambda x: self.build_was_successful(x), build_objs)
        bad = filter(lambda x: self.build_was_successful(x) is False and
                     self.is_running(x) is False, build_objs)
        nr_nab = job_dict['build objects'] - job_dict['still_running']
        job_dict['passes'] = len(good)
        job_dict['fails'] = len(bad)
        job_dict['completed builds'] = nr_nab

        if job not in self.cli.multi_bugs_in_pl:
            # pipeline_deploy 11 active, 16/31 = 58.68% passing
            # Total: 31 builds, 12 active, 2 failed, 17 pass.
            # Success rate: 17 / (31 - 12) = 89%
            success_rate = (float(len(good)) / float(nr_nab) * 100.0
                            if nr_nab else 0)
            job_dict['success rate'] = success_rate
            return job_dict
        else:
            return self.get_passes_fails_from_xml_job(
                job, job_dict, build_objs, bld_artifacts[job])

    def get_passes_fails_from_xml_job(self, job, job_dict, build_objs,
                                      bld_artifacts):
        warnings = []
        msg = "Downloading artifacts for {} ({}% complete)."
        tests = []
        errors = []
        failures = []
        skip = []
        for pos, this_build in enumerate(build_objs):
            build = this_build.get('number')
            artifacts = bld_artifacts.get(build)
            for artifact in artifacts:
                op_dir = self.create_output_directory(job)
                if artifact:
                    op_dir = self.create_output_directory(
                        os.path.join(job, str(build)))
                    artifact_name = str(artifact).split('/')[-1].strip('>')
                    xml_file = os.path.join(op_dir, artifact_name)
                    if not os.path.exists(xml_file):
                        artifact.save_to_dir(op_dir)
                    with open(xml_file):
                        parser = etree.XMLParser(huge_tree=True)
                        try:
                            doc = etree.parse(xml_file, parser).getroot()
                            tests.append(int(doc.attrib.get('tests', 0)))
                            errors.append(int(doc.attrib.get('errors', 0)))
                            failures.append(
                                int(doc.attrib.get('failures', 0)))
                            skip.append(int(doc.attrib.get('skip', 0)))
                        except Exception, e:
                            warnings.append("'{0}' for build {1}"
                                            .format(e, build))
                            continue
                        artifact_rename = ("{0}_{1}.{2}".format(
                                           artifact_name.split('.')[0],
                                           str(build),
                                           artifact_name.split('.')[-1]))
                        os.rename(xml_file, xml_file.replace(
                            artifact_name, artifact_rename))
            pgr = self.calculate_progress(pos, build_objs)
            if pgr:
                self.cli.LOG.info(msg.format(job, pgr))
        if len(warnings) > 0:
            print("The following issue(s) occurred:")
            pprint(set(warnings))
            print("Consider a re-run to avoid incorrect stats.")
        n_total = (sum(tests) - sum(skip))
        n_bad = sum(errors) + sum(failures)
        n_good = n_total - n_bad
        success_rate = ((float(n_good) / n_total) * 100) if n_total else 0
        job_dict['good builds'] = n_good
        job_dict['total'] = sum(tests)
        job_dict['total without skipped'] = n_total
        job_dict['skipped'] = sum(skip)
        job_dict['success rate'] = success_rate
        return job_dict

    def tidy_up(self):
        for op_dir in set(self.op_dirs):
            if os.path.isdir(op_dir):
                shutil.rmtree(op_dir)
                self.cli.LOG.debug("{} deleted".format(op_dir))

    def is_running(self, build):
        return build.get('duration') == 0

    def build_was_successful(self, build):
        return (not self.is_running(build) and build['result'] == 'SUCCESS')

    def calculate_overall_success_rates(self, totals, results):
        all_success_rates = []
        non_xml_success_rates = []
        subset_success_rate = []
        for job, result in results['jobs'].items():
            all_success_rates.append(result.get('success rate', 0))
            if job not in self.cli.multi_bugs_in_pl:
                non_xml_success_rates.append(result.get('success rate', 0))
            if job in self.cli.subset_success_rate_jobs:
                subset_success_rate.append(result.get('success rate', 0))
        results['overall']['combined_subset_sr'] = round(
            self.calculate_percentages(subset_success_rate), 2)
        results['overall']['average_percentage_sr'] = round(
            sum(all_success_rates) / float(len(all_success_rates)), 2)
        results['overall']['combined_sr'] = round(
            self.calculate_percentages(all_success_rates), 2)
        results['overall']['combined_non_xml_sr'] = round(
            self.calculate_percentages(non_xml_success_rates), 2)
        return results

    def calculate_percentages(self, percentages_list):
        combined_percentage_pass = 100
        for pc in percentages_list:
            combined_percentage_pass *= (pc / 100.0)
        return combined_percentage_pass

    def write_intro_to_results_file(self, fname):
        with open(fname, 'w') as fout:
            fout.write(self.intro + ":\n")

    def write_to_results_file(self, fname, results, job):
        job_dict = results['jobs'][job]

        # Write to file:
        with open(fname, 'a') as fout:
            fout.write('\n')
            fout.write("* {} success rate was {}%\n"
                       .format(job, round(job_dict.get('success rate', 0), 2)))
            fout.write("    - Start Job: {} (Date: {})\n"
                       .format(job_dict.get('start job'),
                               job_dict.get('start date')))
            fout.write("    - End Job: {} (Date: {})\n"
                       .format(job_dict.get('end job'),
                               job_dict.get('end date')))
            fout.write("    - {} jobs, {} active, {} pass, {} fail\n"
                       .format(job_dict.get('build objects', 0),
                               job_dict.get('still_running', 0),
                               job_dict.get('passes', 0),
                               job_dict.get('fails', 0)))
            if job in self.cli.multi_bugs_in_pl:
                fout.write("    - {} good tests out of {} "
                           "(There were {} total, but {} were skipped)\n"
                           .format(job_dict.get('good builds', 0),
                                   job_dict.get('total without skipped', 0),
                                   job_dict.get('total', 0),
                                   job_dict.get('skipped', 0)))

    def write_summary_to_results_file(self, fname, totals, results):
        # Write to file:
        with open(fname, 'a') as fout:
            fout.write('\n')
            expl = "{}".format(", ".join(self.cli.subset_success_rate_jobs))
            idx = expl.rfind(',')
            expl = "".join([expl[:idx], " &", expl[idx + 1:]])
            fout.write("Overall Success Rate (pass rate on {} jobs): {}%\n"
                       .format(expl, results['overall']['combined_subset_sr']))
            fout.write("Average Success Rate (mean of all jobs): {}%\n"
                       .format(results['overall']['average_percentage_sr']))
            fout.write('\n')
            fout.write("Overall Success Rate (pass rate on all jobs): {}%\n"
                       .format(results['overall']['combined_sr']))
            fout.write("Overall Success Rate (pass rate on non-xml job): {}%\n"
                       .format(results['overall']['combined_non_xml_sr']))

    def print_results(self, fname):
        """Read back that file and print to console"""
        with open(fname, 'r') as fin:
            print(fin.read())
        print("\n")


def main():
    stats = Stats()
    return stats.message


if __name__ == "__main__":
    sys.exit(main())
