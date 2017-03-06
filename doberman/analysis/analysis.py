#! /usr/bin/env python2

import sys
import os
from datetime import datetime
from jenkinsapi.custom_exceptions import *
from doberman.common.base import DobermanBase
from crude_jenkins import Jenkins, Build
from doberman.analysis.crude_weebl import WeeblClass
from doberman.common.CLI import CLI
# <ACTIONPOINT>
try:
    from weeblclient.weebl import Weebl
except ImportError as e:
    pass
#


class CrudeAnalysis(DobermanBase):

    def __init__(self, cli=False):
        doberman_start_time = datetime.now()
        self.cli = CLI().populate_cli() if not cli else cli
        self.jenkins = Jenkins(self.cli)
        # <ACTIONPOINT>
        if self.cli.use_weebl:
            self.cli.LOG.info("Connecting to Weebl @ {}"
                              .format(self.cli.weebl_url))
            self.weebl = Weebl(
                self.cli.uuid,
                self.cli.environment,
                username=self.cli.weebl_username,
                apikey=self.cli.weebl_apikey,
                weebl_url=self.cli.weebl_url)
            self.weebl.weeblify_environment(
                self.cli.jenkins_host, self.jenkins)
            if self.cli.database != 'None':
                # Use database file:
                self.cli.LOG.info("Loading bugs from database file: %s"
                                  % (self.cli.database))
                self.cli.bugs = self.load_bugs_from_yaml_file(
                    self.cli.database)
            else:
                self.cli.bugs = self.weebl.get_bug_info().get('bugs')
        else:
            self.cli.bugs = None
        #
        self.weebl_tools = WeeblClass(self.cli)
        if self.cli.bugs is None:
            self.cli.bugs = self.weebl_tools.bugs
        self.build_numbers = self.build_pl_ids_and_check(
            self.jenkins, self.weebl_tools)
        jobs_to_process = self.determine_jobs_to_process()
        yamldict, problem_pipelines = self.pipeline_processor(jobs_to_process)
        self.generate_output_files(yamldict, problem_pipelines)
        if not self.cli.offline_mode:
            self.remove_dirs(self.cli.job_names)
        doberman_finish_time = datetime.now()
        self.cli.LOG.info(
            self.report_time_taken(doberman_start_time, doberman_finish_time))

    def determine_jobs_to_process(self):
        """Makes sure it does not process pipeline_start job."""
        if 'crude_job' in self.cli.__dict__:
            jobs_to_process = [j for j in self.cli.job_names
                               if j != self.cli.crude_job]
        else:
            jobs_to_process = self.cli.job_names
        return jobs_to_process

    def pipeline_processor(self, jobs_to_process):
        self.message = 0
        yamldict = {}  # Dict containing info to be written to each job's yaml
        problem_pipelines = []

        if jobs_to_process:
            for job_name in jobs_to_process:
                yamldict[job_name] = {}
        else:
            yamldict['yamldict'] = {}

        progmsg = "Scanning of files is {}% complete."

        for pos, pipeline_id in enumerate(self.pipeline_ids):
            job_dict = {}
            self.pipeline = pipeline_id

            if self.build_numbers == {}:
                raise Exception("Empty build numbers dictionary")

            # Get pipeline data then process each:
            build_numbers = self.build_numbers[pipeline_id]

            # Get pipeline data then process each:
            prev_class = None

            for job in jobs_to_process:
                if build_numbers == '*':
                    build_num = pipeline_id
                else:
                    build_num = build_numbers.get(job)
                if build_num is None:
                    continue

                jdict = job_dict[job] if job in job_dict else {}

                # Pull console and artifacts from jenkins:
                build_obj = Build(build_num, job, self.jenkins, jdict,
                                  self.cli, pipeline_id, prev_class)
                job_dict[job] = build_obj.yaml_dict
                prev_class = build_obj

                if self.message != 1:
                    self.message = getattr(build_obj, 'message', self.message)

            # Notify user of progress:
            pgr = self.calculate_progress(pos, self.pipeline_ids)
            if pgr:
                self.cli.LOG.info(progmsg.format(pgr))

            pl_proc_msg = "CrudeAnalysis has finished processing pipline id: "
            pl_proc_msg += "{0} and is returning a value of {1}.\n\n"
            self.cli.LOG.info(pl_proc_msg.format(pipeline_id, self.message))

            # Merge dictionaries (necessary for multiple pipelines):
            for job_name in yamldict:
                yd = yamldict[job_name].get('pipeline', {})
                if job_name in job_dict:
                    jd = job_dict[job_name].get('pipeline', {})
                else:
                    jd = {}
                to_write_to_file = self.join_dicts(yd, jd)
                yamldict[job_name]['pipeline'] = to_write_to_file

        self.cli.LOG.info(progmsg.format(100))
        return (yamldict, problem_pipelines)

    def generate_output_files(self, yamldict, problem_pipelines):
        # Export to yaml:
        rdir = self.cli.reportdir
        for job_name in yamldict:
            self.export_to_yaml(yamldict[job_name], job_name, rdir)

        # Write to file any pipelines (+ deploy build) that failed processing:
        if not problem_pipelines == []:
            file_path = os.path.join(self.cli.reportdir,
                                     'problem_pipelines.yaml')
            open(file_path, 'a').close()  # Create file if doesn't exist yet
            with open(file_path, 'r+') as pp_file:
                existing_content = pp_file.read()
                pp_file.seek(0, 0)  # Put at beginning of file
                pp_file.write("\n" + str(datetime.now()) +
                              "\n--------------------------\n")
                for problem_pipeline in problem_pipelines:
                    probs = "* {} ({}: {}):\n{}\n\n"
                    pp_file.write(probs.format(*problem_pipeline))
                pp_file.write(existing_content)
                errmsg = "There were some pipelines that could not be "
                errmsg += "processed. This information was written to problem"
                errmsg += "_pipelines.yaml in " + self.cli.reportdir + "\n\n"
                self.cli.LOG.error(errmsg)

        self.log_pipelines()

    def export_to_yaml(self, yaml_dict, job, reportdir):
        """ Write output files. """
        filename = 'triage_' + job + '.yml'
        if not yaml_dict:
            yaml_dict['pipeline'] = {}
        self.write_output_yaml(reportdir, filename, yaml_dict)

    def log_pipelines(self):
        # Record which pipelines were processed in a yaml:
        if self.cli.logpipelines:
            file_path = os.path.join(self.cli.reportdir,
                                     'pipelines_processed.yaml')
            open(file_path, 'a').close()  # Create file if doesn't exist yet
            with open(file_path, 'r+') as pp_file:
                existing_content = pp_file.read()
                pp_file.seek(0, 0)  # Put at beginning of file
                pp_file.write("\n" + str(datetime.now()) +
                              "\n--------------------------\n")
                pp_file.write(" ".join(self.pipeline_ids))
                pp_file.write("\n" + existing_content)
                info_msg = "All processed pipelines recorded to {0}"
                self.cli.LOG.info(info_msg.format(file_path))


def main():
    crude = CrudeAnalysis()
    return crude.message


if __name__ == "__main__":
    sys.exit(main())
