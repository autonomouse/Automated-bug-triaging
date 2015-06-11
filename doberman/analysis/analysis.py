import sys
import os
import shutil
from datetime import datetime
from jenkinsapi.custom_exceptions import *
from doberman.common.common import Common
from crude_jenkins import Jenkins, Deploy, Prepare, Tempest
from crude_test_catalog import TestCatalog
from doberman.common.CLI import CLI


class CrudeAnalysis(Common):
    """

    """

    def __init__(self, cli=False):
        self.cli = CLI().populate_cli() if not cli else cli
        self.jenkins = Jenkins(self.cli)
        self.test_catalog = TestCatalog(self.cli)
        self.build_numbers = self.build_pl_ids_and_check()
        self.pipeline_processor(self.build_numbers)
        if not self.cli.offline_mode:
            self.remove_dirs(self.cli.job_names)

    def build_pl_ids_and_check(self):
        self.pipeline_ids = []
        self.ids = self.cli.ids

        if self.cli.offline_mode:
            self.cli.LOG.info(" *** Offline mode *** ")
            build_numbers = self.test_catalog.get_pipelines_from_paabn()
            self.ids = build_numbers.keys()

        elif self.cli.use_deploy:
            # If using build numbers instead of pipelines, get pipeline:
            msg = "Looking up pipeline ids for the following jenkins "
            msg += "pipeline_deploy build numbers: %s"
            self.cli.LOG.info(msg % ", ".join([str(i) for i in self.cli.ids]))

            # Expand out id numbers if a range has been used:
            exp_ids = []
            for idn in self.ids:
                if '-' in idn:
                    range_start = int(idn.split('-')[0])
                    range_end = int(idn.split('-')[-1]) + 1
                    exp_range = [str(b) for b in range(range_start, range_end)]
                    exp_ids.extend(exp_range)
                else:
                    exp_ids.append(idn)
            self.ids = set(exp_ids)

        elif self.cli.use_date_range:
            # If using a date range instead of pipelines, get pipeline:
            msg = "Getting pipeline ids for between {0} and {1} (this locale)"
            self.cli.LOG.info(msg.format(self.cli.start.strftime('%c'),
                                         self.cli.end.strftime('%c')))
            self.ids = self.test_catalog.get_pipelines_from_date_range()

        for pos, idn in enumerate(self.ids):
            if self.cli.use_deploy:
                try:
                    pipeline = \
                        self.test_catalog.get_pipeline_from_deploy_build(idn)
                except:
                    # Fall back to jenkins if test-catalog is down:
                    pipeline = self.jenkins.get_pipeline_from_deploy_build(idn)
            else:
                pipeline = idn
            # Quickly cycle through to check all pipelines are real:
            if not self.jenkins.pipeline_check(pipeline):
                msg = "Pipeline ID \"%s\" is an unrecognised format" % pipeline
                self.cli.LOG.error(msg)
            else:
                self.pipeline_ids.append(pipeline)

            # Notify user of progress:
            pgr = self.calculate_progress(pos, self.ids)
            if pgr:
                self.cli.LOG.info("Pipeline lookup {0}% complete.".format(pgr))
        msg = "Pipeline lookup 100% complete: All pipelines checked. "
        msg += "Now polling jenkins and processing data."
        self.cli.LOG.info(msg)
        return self.test_catalog.get_all_pipelines(self.pipeline_ids)

    def remove_dirs(self, folders_to_remove):
        """ Remove data folders used to store untarred artifacts (just leaving
            yaml files).

        """

        if type(folders_to_remove) not in [list, tuple, dict]:
            folders_to_remove = [folders_to_remove]

        if not self.cli.keep_data:
            for folder in folders_to_remove:
                kill_me = os.path.join(self.cli.reportdir, folder)
                if os.path.isdir(kill_me):
                    shutil.rmtree(kill_me)

    def pipeline_processor(self, build_numbers):

        self.message = 1
        deploy_yamldict = {}
        prepare_yamldict = {}
        tempest_yamldict = {}
        problem_pipelines = []

        for pipeline_id in self.pipeline_ids:
            deploy_dict = {}
            prepare_dict = {}
            tempest_dict = {}
            self.pipeline = pipeline_id

            try:
                # Get pipeline data then process each:
                deploy_build = build_numbers[pipeline_id]['pipeline_deploy']
                prepare_build = build_numbers[pipeline_id]['pipeline_prepare']
                tempest_build = \
                    build_numbers[pipeline_id]['test_tempest_smoke']

                # Pull console and artifacts from jenkins:
                deploy = Deploy(deploy_build, 'pipeline_deploy', self.jenkins,
                                deploy_dict, self.cli,
                                self.test_catalog.bugs, pipeline_id)
                deploy_dict = deploy.yaml_dict
                self.message = deploy.message

                if prepare_build:
                    prepare = Prepare(prepare_build, 'pipeline_prepare',
                                      self.jenkins, prepare_dict,
                                      self.cli, self.test_catalog.bugs,
                                      pipeline_id, deploy)
                    prepare_dict = prepare.yaml_dict
                    if self.message != 1:
                        self.message = prepare.message

                if tempest_build:
                    tempest = Tempest(tempest_build, 'test_tempest_smoke',
                                      self.jenkins, tempest_dict,
                                      self.cli, self.test_catalog.bugs,
                                      pipeline_id, prepare)
                    tempest_dict = tempest.yaml_dict
                    if self.message != 1:
                        self.message = tempest.message

            except Exception as e:
                if 'deploy_build' not in locals():
                    msg = "Cannot acquire pipeline deploy build number"
                    msg += " (may be cookie related?)"
                else:
                    probmsg = "Problem with {} - skipping "
                    if deploy_build:
                        probmsg += "(deploy_build: {})"
                    self.cli.LOG.error(probmsg.format(pipeline_id,
                                                      deploy_build))
                    problem_pipelines.append((pipeline_id, deploy_build, e))
                self.cli.LOG.exception(e)

            pl_proc_msg = "CrudeAnalysis has finished processing pipline id: "
            pl_proc_msg += "{0} and is returning a value of {1}."
            self.cli.LOG.info(pl_proc_msg.format(pipeline_id, self.message))

            # Merge dictionaries (necessary for multiple pipelines):
            deploy_yamldict['pipeline'] = \
                self.join_dicts(deploy_yamldict.get('pipeline', {}),
                                deploy_dict.get('pipeline', {}))
            prepare_yamldict['pipeline'] = \
                self.join_dicts(prepare_yamldict.get('pipeline', {}),
                                prepare_dict.get('pipeline', {}))
            tempest_yamldict['pipeline'] = \
                self.join_dicts(tempest_yamldict.get('pipeline', {}),
                                tempest_dict.get('pipeline', {}))

        # Export to yaml:
        rdir = self.cli.reportdir
        self.export_to_yaml(deploy_yamldict, 'pipeline_deploy', rdir)
        self.export_to_yaml(prepare_yamldict, 'pipeline_prepare', rdir)
        self.export_to_yaml(tempest_yamldict, 'test_tempest_smoke', rdir)

        # Write to file any pipelines (+ deploy build) that failed processing:
        if not problem_pipelines == []:
            file_path = os.path.join(self.cli.reportdir,
                                     'problem_pipelines.yaml')
            open(file_path, 'a').close()  # Create file if doesn't exist yet
            with open(file_path, 'r+') as pp_file:
                existing_content = pp_file.read()
                pp_file.seek(0, 0)  # Put at beginning of file
                pp_file.write("\n" + str(datetime.now())
                              + "\n--------------------------\n")
                for problem_pipeline in problem_pipelines:
                    probs = "* %s (deploy build: %s):\n%s\n\n"
                    pp_file.write(probs % problem_pipeline)
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


def main():
    crude = CrudeAnalysis()
    return crude.message


if __name__ == "__main__":
    sys.exit(main())
