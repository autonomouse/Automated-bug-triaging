import os
import yaml
from weeblclient.weebl_python2.weebl import Weebl
from doberman.common import pycookiecheat
from doberman.common.base import DobermanBase
from jenkinsapi.custom_exceptions import *


class WeeblClass(DobermanBase):

    def __init__(self, cli, bugs=None):
        self.cli = cli
        self.verify = self.cli.verify
        self.bugs = None
        self.weebl = None
        if not self.cli.offline_mode:
            self.weebl = self.get_weebl_client()
        if bugs is not None:
            self.bugs = bugs.get('bugs')
        else:
            self.open_bug_database()

    def open_bug_database(self):
        if self.cli.database in [None, 'None', 'none', '']:
            if not self.cli.offline_mode:
                self.bugs = self.weebl.get_bug_info()['bugs']
            else:
                emsg = "In offline mode, but no local database file provided!!"
                self.cli.LOG.error(emsg)
                raise Exception(emsg)
        elif len(self.cli.database):
            self.cli.LOG.info("Loading bugs from database file: %s"
                              % (self.cli.database))
            self.bugs = self.load_bugs_from_yaml_file(self.cli.database)
        else:
            self.cli.LOG.error('Unknown database: %s' % (self.cli.database))
            raise Exception('Invalid Database configuration')

    def get_weebl_client(self):
        return Weebl(
            uuid=self.cli.uuid,
            env_name=self.cli.environment,
            username=self.cli.weebl_username,
            apikey=self.cli.weebl_apikey,
            weebl_url=self.cli.weebl_url,
            weebl_api_ver="v1")

    def get_pipelines_from_paabn(self, filename=None):
        if not filename:
            filename = 'pipelines_and_associated_build_numbers.yml'
        if filename in os.listdir(self.cli.reportdir):
            with open(os.path.join(self.cli.reportdir, filename), "r") as f:
                return yaml.load(f)
        return {}

    def get_all_pipelines(self, pipeline_ids):
        build_numbers = {}
        self.mkdir(self.cli.reportdir)

        # The local dictionary way:
        filename = 'pipelines_and_associated_build_numbers.yml'
        build_numbers = self.get_pipelines_from_paabn(filename)

        # Check that all pipeline_ids were in the yaml file:
        if build_numbers:
            missing = [pl for pl in pipeline_ids if pl not in
                       build_numbers.keys()]
        else:
            missing = pipeline_ids

        if missing:
            # The test catalog way:
            checkin = 5 if len(missing) > 20 else None
            for pos, pipeline_id in enumerate(missing):
                pldata = self.get_pipelines(pipeline_id)
                if pldata:
                    build_numbers[pipeline_id] = pldata
                pgr = self.calculate_progress(pos, missing, checkin)
                if pgr:
                    self.cli.LOG.info(
                        "Build lookup {0}% complete.".format(pgr))

            # Create local dictionary for next time:
            self.write_output_yaml(self.cli.reportdir, filename, build_numbers)

        # Remove any pipelines that shouldn't be there (keep in the paabn
        # though - no need to lose good data):
        not_these = [pl for pl in build_numbers.keys() if pl not in
                     pipeline_ids]
        [build_numbers.pop(not_this) for not_this in not_these]

        self.cli.LOG.info("Returning {} pipelines".format(len(build_numbers)))
        return build_numbers

    def get_pipelines(self, pipeline):
        """ Using test-catalog, return the build numbers for the jobs that are
            part of the given pipeline.
        """
        try:
            weebl_pipeline = self.weebl.resources.pipeline.get(uuid=pipeline)
        except ValueError as e:
            msg = "Weebl error. Does pipeline exist? (%s)" % e
            self.cli.LOG.error(msg)
            return

        build_numbers = {}

        for jname in self.cli.job_names:
            try:
                weebl_build = self.weebl.resources.build.get(
                    pipeline__uuid=pipeline, jobtype__name=jname)
                build_numbers[jname] = weebl_build['build_id']
            except:
                build_numbers[jname] = None
        bstr = ", ".join(["{} ({})".format(val, key)
                          for key, val in build_numbers.items() if val])
        msg = 'Build numbers {1} associated with pipeline: {0}'
        self.cli.LOG.debug(msg.format(pipeline, bstr))
        return build_numbers

    def get_pipelines_from_date_range(self, start, end, limit=2000,
                                      ts_format='%Y-%m-%dT%H:%M:%S.%sZ'):
        pipeline_objects = self.weebl.resources.pipeline.objects(
            completed_at__gte=start.strftime(ts_format),
            completed_at__lte=end.strftime(ts_format),
            limit=limit)
        return [obj['uuid'] for obj in pipeline_objects]
