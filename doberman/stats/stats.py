#! /usr/bin/env python2

import os
import yaml
import arrow
import bisect
import shutil
from lxml import etree
from arrow import Arrow
from stats_cli import CLI
from doberman.common.common import Common
from doberman.analysis.crude_jenkins import Jenkins
from doberman.analysis.crude_test_catalog import TestCatalog


class Stats(Common):

    def __init__(self, cli=False):
        self.cli = CLI().populate_cli() if not cli else cli
        self.test_catalog = TestCatalog(self.cli)
        self.jenkins = Jenkins(self.cli)
        self.jenkins_api = self.jenkins.jenkins_api
        self.main()

    def main(self):
        self.cli.LOG.info("Data for OIL Environment: {} (Jenkins host: {})"
                          .format(self.cli.environment, self.cli.jenkins_host))
        self.op_dir = self.create_output_directory()
        self.build_numbers = self.build_pl_ids_and_check(
            self.jenkins, self.test_catalog)

        # Set up output dict:
        results = {'jobs': {}, 'overall': {}}
        totals = {}
        triage = {}

        # Calculate totals:
        builds = self.get_builds()
        for job in self.cli.job_names:
            if job == self.cli.crude_job:
                self.cli.LOG.debug("Skipping {} job".format(job))
                continue
            self.cli.LOG.debug("{}:".format(job))
            job_dict, nr_nab = self.populate_job_dict(job, builds[job])
            results['jobs'][job] = job_dict
            totals[job] = {'total_builds': nr_nab,
                           'passing': job_dict.get('passes', 0)}
            triage[job] = job_dict.get('fails', 0)

        # Report results:
        fname = os.path.join(self.cli.reportdir, "stats.txt")
        open(fname, 'w').close
        for job in self.cli.job_names:
            if job == self.cli.crude_job:
                continue
            # I wanted to do "for job in results.keys():" here, but then they
            # wouldn't be reported in the correct order.
            self.write_to_results_file(fname, results, job)

        # Overall success:
        self.write_summary_to_results_file(fname, totals, results)

        # Save results to file:
        self.generate_output_file(results)

        self.print_results(fname)

        # Triage report
        if self.cli.triage:
            print('Running triage_report')
            self.triage_report(triage, self.cli.start, self.cli.end,
                               self.jenkins_api)

        # Clean up:
        if not self.cli.keep_data:
            self.tidy_up()

    def create_output_directory(self):
        op_dir = os.path.abspath(os.path.join(
            self.cli.reportdir, "stats"))
        self.mkdir(op_dir)
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
        pipelines_to_remove = []
        for job in self.cli.job_names:
            if job == self.cli.crude_job:
                self.cli.LOG.debug("Skipping {} job".format(job))
                continue
            jenkins_job = self.jenkins_api[job]
            self.cli.LOG.info("Polling Jenkins for {} data".format(job))
            all_builds[job] = jenkins_job._poll()['builds']
            for pipeline, build_dict in self.build_numbers.items():
                build_number = build_dict[job]
                if build_number is None:
                    continue
                this_build = [b for b in all_builds[job] if b['number']
                              == int(build_number)][0]
                if self.is_running(this_build):
                    pipelines_to_remove.append(pipeline)
                    self.cli.LOG.info("{} build {} is still running"
                                      .format(job, this_build['number']))
        for pipeline in set(pipelines_to_remove):
            self.build_numbers.pop(pipeline)

        for job in self.cli.job_names:
            if job == self.cli.crude_job:
                self.cli.LOG.debug("Skipping {} job".format(job))
                continue
            completed_builds = [
                int(bs[job]) for pl, bs in self.build_numbers.items()
                if bs[job] is not None]
            builds[job] = [b for b in all_builds[job] if b['number'] in
                           completed_builds]
        return builds

    def get_start_idx_num_and_date(self, builds,
                                   ts_format='YYYY-MMM-DD HH:mm:ss'):
        start_idx = self.find_build_newer_than(builds, self.cli.start)
        end_idx = self.find_build_newer_than(builds, self.cli.end)

        # end date is newer than we have builds, just use
        # the most recent build.
        if end_idx is None and start_idx is None:
            start_idx = builds.index(builds[-1])

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

    def get_num_builds_and_active(self, builds, start_idx, end_idx):
        builds_to_check = [r['number'] for r in builds[start_idx:end_idx]]

        build_objs = [b for b in builds if b['number'] in builds_to_check]
        active = filter(lambda x: self.is_running(x) is True, build_objs)

        return len(builds_to_check), len(active), build_objs

    def populate_job_dict(self, job, builds):
        job_dict = {}
        if builds is None:
            nr_nab = 0
            return job_dict, nr_nab

        start_idx, start_num, start_date =\
            self.get_start_idx_num_and_date(builds)
        end_idx, end_num, end_date = self.get_end_idx_num_and_date(builds)
        job_dict['start job'] = start_num
        job_dict['end job'] = end_num
        job_dict['start date'] = start_date
        job_dict['end date'] = end_date

        # From idx to end:
        nr_builds, num_active, build_objs = self.get_num_builds_and_active(
            builds, start_idx, end_idx)
        job_dict['build objects'] = nr_builds
        if job not in self.cli.xmls:
            job_dict = self.get_passes_fails_from_non_xml_job(
                job_dict, build_objs, num_active)
        else:
            job_dict = self.get_passes_fails_from_xml_job(job_dict)

        nr_nab = job_dict['build objects'] - num_active
        msg = "There are {} {} builds"
        if num_active != 0:
            msg += "(ignoring {} builds that are still active)"
        self.cli.LOG.info(msg.format(nr_nab, job, num_active))
        return job_dict, nr_nab

    def get_passes_fails_from_non_xml_job(self, job_dict, build_objs,
                                          num_active):
        # TODO: handle case where we don't have active, good or bad builds

        good = filter(lambda x: self.is_good(x), build_objs)
        bad = filter(lambda x: self.is_good(x) is False and
                     self.is_running(x) is False, build_objs)
        nr_nab = job_dict['build objects'] - num_active
        success_rate = (float(len(good)) / float(nr_nab) * 100.0
                        if nr_nab else 0)
        # pipeline_deploy 11 active, 16/31 = 58.68% passing
        # Total: 31 builds, 12 active, 2 failed, 17 pass.
        # Success rate: 17 / (31 - 12) = 89%
        job_dict['passes'] = len(good)
        job_dict['fails'] = len(bad)
        job_dict['completed builds'] = nr_nab
        job_dict['success rate'] = success_rate

        return job_dict

    def get_passes_fails_from_xml_job(self, job_dict):
        tests = []
        errors = []
        failures = []
        skip = []
        import pdb; pdb.set_trace()
        for build in [bld['number'] for bld in builds[start_idx:end_idx]]:
            this_build = jenkins_job.get_build(build)
            artifacts = [b for b in this_build.get_artifacts()
                         if 'tempest_xunit.xml>' in str(b)]
            artifact = artifacts[0] if artifacts else None
            if artifact:
                artifact_name = str(artifact).split('/')[-1].strip('>')
                xml_file = os.path.join(self.op_dir, artifact_name)
                with open(artifact.save_to_dir(self.op_dir)):
                    parser = etree.XMLParser(huge_tree=True)
                    try:
                        doc = etree.parse(xml_file, parser).getroot()
                        tests.append(int(doc.attrib.get('tests', 0)))
                        errors.append(int(doc.attrib.get('errors', 0)))
                        failures.append(int(doc.attrib.get('failures', 0)))
                        skip.append(int(doc.attrib.get('skip', 0)))
                    except Exception, e:
                        print("'{0}' for build {1}".format(e, build))
                        print("Consider a re-run to avoid incorrect stats")
                        continue
                    artifact_rename = ("{0}_{1}.{2}".format(
                                       artifact_name.split('.')[0],
                                       str(build),
                                       artifact_name.split('.')[-1]))
                    os.rename(xml_file, xml_file.replace(artifact_name,
                                                         artifact_rename))
        n_total = (sum(tests) - sum(skip))
        n_good = n_total - (sum(errors) + sum(failures))
        success_rate = (round((float(n_good) / n_total) * 100, 2)
                        if n_total else 0)
        job_dict['good builds'] = n_good
        job_dict['total'] = n_total
        job_dict['total without skipped'] = sum(tests)
        job_dict['skipped'] = sum(skip)
        job_dict['success rate'] = success_rate
        return job_dict

    def tidy_up(self):
        if os.path.isdir(self.op_dir):
            self.cli.LOG.info("{} deleted".format(self.op_dir))
            shutil.rmtree(self.op_dir)

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
        return build['duration'] == 0

    def is_good(self, build):
        return (not self.is_running(build) and build['result'] == 'SUCCESS')

    def triage_report(self, triage, start, end, jenkins,
                      ts_format='YYYY-MMM-DD HH:mm:ss'):
        """Collect data on failed builds
        for each job in the triage dictionary
            look at each job and extract:
                - console text
                - all artifacts
        write out report to oil-triage-START-END/<job>/<buildno>/<artifacts>

        param triage: dictionary with job names as keys, value
                      is a list of jenkins build objects
        """
        self.cli.LOG.info('Collecting debugging data...')
        srtdate = Arrow.utcfromtimestamp(
            arrow.get(self.cli.start).timestamp).format(ts_format)
        enddate = Arrow.utcfromtimestamp(
            arrow.get(self.cli.end).timestamp).format(ts_format)

        report_subdir = "oil-triage-{}-{}".format(srtdate, enddate)
        report_loc = os.path.join(self.op_dir, report_subdir)
        for job in triage.keys():
            jenkins_job = jenkins[job]
            for b in triage[job]:
                build = jenkins_job.get_build(b['number'])
                outdir = os.path.join(report_loc, job, str(b['number']))
                try:
                    os.makedirs(outdir)
                except OSError:
                    if not os.path.isdir(outdir):
                        raise
                with open(os.path.join(outdir, "console.txt"), "w") as c:
                    self.cli.LOG.info('Saving console @ {} to {}'.format(
                        build.baseurl, outdir))
                    console = build.get_console()
                    c.write(console)
                    c.write('\n')
                    c.flush()

                for a in build.get_artifacts():
                    a.save_to_dir(outdir)

    def write_to_results_file(self, fname, results, job):
        job_dict = results['jobs'][job]

        success_rate = round(job_dict.get('success rate', 0), 2)

        # Write to file:
        with open(fname, 'a') as fout:
            fout.write('\n')
            fout.write("* {} success rate was {}%\n"
                       .format(job, success_rate))
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
        success_rate = self.calculate_overall_success_rate(totals, results)

        # Write to file:
        with open(fname, 'a') as fout:
            fout.write('\n')
            fout.write("Overall Success Rate: {}%\n".format(success_rate))
            fout.write("    - {} tempest builds out of {} total jobs\n"
                       .format(results['overall'].get('tempest builds'),
                               results['overall'].get('total jobs')))

    def print_results(self, fname):
        """Read back that file and print to console"""
        with open(fname, 'r') as fin:
            print fin.read()

    def calculate_overall_success_rate(self, totals, results):
        if self.cli.summary:
            tt = totals['test_tempest_smoke']['total_builds']
            td = totals['pipeline_deploy']['total_builds']
            overall = (float(tt) / float(td) * 100.0) if td else 0

            results['overall']['success rate'] = overall
            results['overall']['tempest builds'] = tt
            results['overall']['total jobs'] = td
        unrounded_success_rate = results['overall'].get('success rate')
        sr = round(unrounded_success_rate, 2) if unrounded_success_rate else 0
        return sr

if __name__ == '__main__':
    Stats()
