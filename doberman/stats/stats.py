#! /usr/bin/env python2

import os
import sys
import yaml
import arrow
import bisect
import shutil
from lxml import etree
from arrow import Arrow
from stats_cli import CLI
from pprint import pprint
from doberman.common.common import Common
from doberman.analysis.crude_jenkins import Jenkins
from doberman.analysis.crude_test_catalog import TestCatalog


class Stats(Common):

    def __init__(self, cli=False):
        self.message = 1
        stats_start_time = arrow.now()
        self.cli = CLI().populate_cli() if not cli else cli
        self.test_catalog = TestCatalog(self.cli)
        self.jenkins = Jenkins(self.cli)
        self.jenkins_api = self.jenkins.jenkins_api
        self.op_dirs = []
        self.run_stats()
        stats_finish_time = arrow.now()
        self.cli.LOG.info(self.report_time_taken(
            stats_start_time, stats_finish_time))
        self.message = 0

    def run_stats(self):
        self.cli.LOG.info("Data for OIL Environment: {} (Jenkins host: {})"
                          .format(self.cli.environment, self.cli.jenkins_host))
        self.build_numbers = self.build_pl_ids_and_check(
            self.jenkins, self.test_catalog)

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
        fname = os.path.join(self.cli.reportdir, "stats.txt")
        open(fname, 'w').close
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
        for job in self.non_crude_job_names:
            jenkins_job = self.jenkins_api[job]
            self.cli.LOG.info("Polling Jenkins for {} data".format(job))
            all_builds[job] = jenkins_job._poll()['builds']
            actives[job] = []
            for pipeline, build_dict in self.build_numbers.items():
                build_number = build_dict[job]
                if build_number is None:
                    continue

                if self.cli.triage:
                    op_dir = self.create_output_directory(job)
                    self.jenkins.get_triage_data(build_number, job, op_dir)

                try:
                    this_build = [b for b in all_builds[job] if b['number']
                                  == int(build_number)][0]
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

                        all_artifacts.append(artifacts)
                    bld_artifacts[job][this_build['number']] =\
                        all_artifacts if all_artifacts else []

        for pipeline in set(pipelines_to_remove):
            self.build_numbers.pop(pipeline)

        for job in self.non_crude_job_names:
            completed_builds = [
                int(bs[job]) for pl, bs in self.build_numbers.items()
                if bs[job] is not None]
            builds[job] = [b for b in all_builds[job] if b['number'] in
                           completed_builds]
        return builds, actives, bld_artifacts

    def get_start_idx_num_and_date(self, builds,
                                   ts_format='YYYY-MMM-DD HH:mm:ss'):
        start_idx = self.find_build_newer_than(builds, self.cli.start)
        end_idx = self.find_build_newer_than(builds, self.cli.end)
        if end_idx is None and start_idx is None:
            msg = "There were no builds in this time range."
            self.cli.LOG.error(msg)
            raise Exception(msg)
        start_num = builds[start_idx]['number']
        start_in_ms = builds[start_idx]['timestamp'] / 1000
        start_date = Arrow.utcfromtimestamp(start_in_ms).format(ts_format)

        return (start_idx, start_num, start_date)

    def get_end_idx_num_and_date(self, builds,
                                 ts_format='YYYY-MMM-DD HH:mm:ss'):
        end_idx = self.find_build_newer_than(builds, self.cli.end)

        if end_idx is None:
            end_idx = builds.index(builds[-1])

        end_num = builds[end_idx]['number']
        end_in_ms = builds[end_idx]['timestamp'] / 1000
        end_date = Arrow.utcfromtimestamp(end_in_ms).format(ts_format)

        return (end_idx, end_num, end_date)

    def populate_job_dict(self, job, all_builds, all_actives, bld_artifacts):
        job_dict = {}
        builds = all_builds[job]
        num_active = len(all_actives[job])
        job_dict['still_running'] = num_active
        if builds is None:
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
        if job not in self.cli.multi_bugs_in_pl:
            return self.get_passes_fails_from_non_xml_job(job_dict, build_objs)
        else:
            return self.get_passes_fails_from_xml_job(
                job, job_dict, build_objs, bld_artifacts[job])

    def get_passes_fails_from_non_xml_job(self, job_dict, build_objs):
        # TODO: handle case where we don't have active, good or bad builds
        good = filter(lambda x: self.build_was_successful(x), build_objs)
        bad = filter(lambda x: self.build_was_successful(x) is False and
                     self.is_running(x) is False, build_objs)
        nr_nab = job_dict['build objects'] - job_dict['still_running']
        job_dict['passes'] = len(good)
        job_dict['fails'] = len(bad)
        job_dict['completed builds'] = nr_nab

        # pipeline_deploy 11 active, 16/31 = 58.68% passing
        # Total: 31 builds, 12 active, 2 failed, 17 pass.
        # Success rate: 17 / (31 - 12) = 89%
        success_rate = (float(len(good)) / float(nr_nab) * 100.0
                        if nr_nab else 0)
        job_dict['success rate'] = success_rate
        return job_dict

    def get_passes_fails_from_xml_job(self, job, job_dict, build_objs,
                                      bld_artifacts):
        warnings = []
        self.cli.LOG.info("Downloading artifacts for {}".format(job))
        tests = []
        errors = []
        failures = []
        skip = []
        for this_build in build_objs:
            build = this_build['number']
            for artifacts in bld_artifacts:
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
        if len(warnings) > 0:
            print("The following issue(s) occurred:")
            pprint(warnings)
            print("Consider a re-run to avoid incorrect stats.")
        n_total = (sum(tests) - sum(skip))
        n_bad = sum(errors) + sum(failures)
        n_good = n_total - n_bad
        success_rate = ((float(n_good) / n_total) * 100) if n_total else 0
        job_dict['good builds'] = n_good
        job_dict['fails'] = n_bad
        job_dict['passes'] = n_good
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

    def find_build_newer_than(self, builds, timestamp):
        """Finds builds newer than timestamp. It assumes that builds has first
        been sorted.
        """
        # pre calculate key list
        keys = [r.get('timestamp') for r in builds]

        # make a micro timestamp from input
        timestamp_in_ms = arrow.get(timestamp).timestamp * 1000

        # find leftmost item greater than or equal to start
        idx = bisect.bisect_left(keys, timestamp_in_ms)
        if idx != len(keys):
            return idx
        return None

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
        results['overall']['average_percentage_sr'] = round(
            sum(all_success_rates) / float(len(all_success_rates)), 2)
        results['overall']['combined_sr'] = round(
            self.calculate_percentages(all_success_rates), 2)
        results['overall']['combined_non_xml_sr'] = round(
            self.calculate_percentages(non_xml_success_rates), 2)
        results['overall']['combined_subset_sr'] = round(
            self.calculate_percentages(subset_success_rate), 2)
        return results

    def calculate_percentages(self, percentages_list):
        combined_percentage_pass = 100
        for pc in percentages_list:
            combined_percentage_pass *= (pc / 100.0)
        return combined_percentage_pass

    def write_to_results_file(self, fname, results, job):
        job_dict = results['jobs'][job]

        # Write to file:
        with open(fname, 'a') as fout:
            fout.write('\n')
            fout.write("* {} success rate was {}%\n"
                       .format(job, job_dict.get('success rate')))
            fout.write("    - Start Job: {} (Date: {})\n"
                       .format(job_dict.get('start job'),
                               job_dict.get('start date')))
            fout.write("    - End Job: {} (Date: {})\n"
                       .format(job_dict.get('end job'),
                               job_dict.get('end date')))
            if job not in self.cli.xmls:
                fout.write("    - {} jobs, {} active, {} pass, {} fail\n"
                           .format(job_dict.get('build objects'),
                                   job_dict.get('still running'),
                                   job_dict.get('passes'),
                                   job_dict.get('fails')))
            else:
                fout.write("    - {} good / {} ({} total - {} skip)\n"
                           .format(job_dict.get('good builds'),
                                   job_dict.get('total'),
                                   job_dict.get('total without skipped'),
                                   job_dict.get('skipped')))

    def write_summary_to_results_file(self, fname, totals, results):
        # Write to file:
        with open(fname, 'a') as fout:
            fout.write('\n')
            fout.write("Average Success Rate (mean of all jobs): {}%\n"
                       .format(results['overall']['average_percentage_sr']))
            fout.write("Overall Success Rate (pass rate on all jobs): {}%\n"
                       .format(results['overall']['combined_sr']))
            fout.write("Overall Success Rate (pass rate on non-xml job): {}%\n"
                       .format(results['overall']['combined_non_xml_sr']))
            expl = "{}".format(", ".join(self.cli.subset_success_rate_jobs))
            idx = expl.rfind(',')
            expl = "".join([expl[:idx], " &", expl[idx + 1:]])
            fout.write("Overall Success Rate (pass rate on {} jobs): {}%\n"
                       .format(expl, results['overall']['combined_subset_sr']))

    def print_results(self, fname):
        """Read back that file and print to console"""
        with open(fname, 'r') as fin:
            print fin.read()


def main():
    stats = Stats()
    return stats.message


if __name__ == "__main__":
    sys.exit(main())
