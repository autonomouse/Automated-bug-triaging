import os
import tarfile
import bisect
import time
from doberman.analysis.file_parser import FileParser
from jenkinsapi.jenkins import Jenkins as JenkinsAPI
from doberman.common import pycookiecheat
from doberman.common.common import Common
from doberman.analysis.oil_spill import OilSpill
from jenkinsapi.custom_exceptions import *


class Jenkins(Common):

    def __init__(self, cli):
        self._jenkins = []
        self.cli = cli
        self.netloc = self.cli.netloc
        self.cookie = None
        if not self.cli.offline_mode:
            self.connect_to_jenkins()
            try:
                self._jenkins.append(self.jenkins_api)
                self.cli.LOG.info("Succesfully connected to Jenkins")
            except:
                msg = "Problem connecting to Jenkins (try refreshing cookies?)"
                self.cli.LOG.error(msg)
                raise Exception(msg)

    def connect_to_jenkins(self):
        """ Connects to jenkins via jenkinsapi, returns a jenkins object. """

        url = self.cli.jenkins_host
        remote = self.cli.run_remote
        pysid = self.cli.pysid
        self.cli.LOG.debug('Connecting to jenkins @ {0} remote={1}'.format(url,
                           remote))

        if pysid:
            self.cli.LOG.info("Using pysid for jenkins cookie: %s" % pysid)
            self.cookie = {'pysid': pysid}
        elif remote:
            self.cli.LOG.info("Fetching cookies for %s" % url)
            self.cookie = pycookiecheat.chrome_cookies(url)
        try:
            self.jenkins_api = JenkinsAPI(baseurl=url, cookies=self.cookie,
                                          netloc=self.netloc)
        except JenkinsAPIException:
            self.cli.LOG.exception('Failed to connect to Jenkins')

    def get_pipeline_from_deploy_build(self, id_number):
        deploy_bld_n = int(id_number)
        try:
            deploy = self.jenkins_api['pipeline_deploy']
            cons = deploy.get_build(deploy_bld_n).get_console()
        except:
            if self.cli.use_deploy:
                msg = "'{0}' is an unrecognised pipeline_deploy build number"
            else:
                msg = "Failed to fetch pipeline from deploy build: \"{0}\" - "
                msg += "if this is already a pipeline id, run without the '-b'"
                msg += " flag."
            self.cli.LOG.exception(msg.format(deploy_bld_n))
            return
        pl_plus_fluff = cons.split('pipeline_id')[1].split('|\n')[0]
        pl = pl_plus_fluff.replace('|', '').strip()
        if self.pipeline_check(pl):
            return pl
        else:
            pl = cons.split('PIPELINE_ID=')[1].replace('\n++ ', '')
            if self.pipeline_check(pl):
                return pl
            else:
                msg = "Pipeline ID \"%s\" is an unrecognised format" % pl
                self.cli.LOG.error(msg)
                raise Exception(msg)

    def pipeline_check(self, pipeline_id):
        try:
            return [8, 4, 4, 4, 12] == [len(x) for x in pipeline_id.split('-')]
        except:
            return False

    def write_console_to_file(self, build, outdir, jobname):
        console_path = os.path.join(outdir, "{}_console.txt".format(jobname))
        with open(console_path, "w") as cnsl:
            self.cli.LOG.debug('Saving console @ {0} to {1}'.format(
                               build.baseurl, outdir))
            console = build.get_console()
            cnsl.write(console)
            cnsl.write('\n')
            cnsl.flush()

    def find_build_newer_than(self, builds, start):
        """
        assumes builds has been sorted
        """

        # pre calculate key list
        keys = [r['timestamp'] for r in builds]

        # make a micro timestamp from input
        start_ts = int(time.mktime(start.timetuple())) * 1000

        # find leftmost item greater than or equal to start
        i = bisect.bisect_left(keys, start_ts)
        if i != len(keys):
            return i

        self.cli.LOG.error("No job newer than %s" % (start))
        return None

    def get_triage_data(self, build_num, job, reportdir, console_only=False):
        """ Get the artifacts from jenkins via jenkinsapi object. """
        jenkins_job = self.jenkins_api[job]
        build = jenkins_job.get_build(int(build_num))
        outdir = os.path.join(self.cli.reportdir, job, str(build_num))

        # Check to make sure it is not still running!:
        if build._data['duration'] == 0:
            return True  # Still running
        try:
            os.makedirs(outdir)
        except OSError:
            if not os.path.isdir(outdir):
                raise
        self.write_console_to_file(build, outdir, job)

        if not console_only:
            for artifact in build.get_artifacts():
                # No need to get console now:
                if "/console.txt" not in str(artifact):
                    artifact.save_to_dir(outdir)
                    self.extract_and_delete_archive(outdir, artifact)
        return False  # Not still running

    def extract_and_delete_archive(self, outdir, artifact):
        """ Extracts the contents of a tarball and places it into a new file
            of the samename without the .tar.gz suffix (N.B. this leaves
            .ring.gz intact as they seem to contain binary ring files that
            I'm not sure what to do with at this point).

        """
        try:
            if 'tar.gz' in artifact.filename:
                path_to_artifact = os.path.join(outdir, artifact.filename)
                with tarfile.open(path_to_artifact, 'r:gz') as tar:
                    tarlist = [member for member in tar.getmembers()
                               if member.isfile()]
                    for compressed_file in tarlist:
                        slug = compressed_file.name.replace('/', '_')
                        with open(os.path.join(outdir, slug), 'w') as new_file:
                            data = tar.extractfile(compressed_file).readlines()
                            new_file.writelines(data)
                os.remove(os.path.join(outdir, artifact.filename))
        except:
            self.cli.LOG.error("Could not extract %s" % artifact.filename)


class Build(OilSpill):
    """
    """

    def __init__(self, build_number, jobname, jenkins, yaml_dict, cli,
                 pipeline, prev=None):
        super(Build, self).__init__(build_number, jobname, yaml_dict, cli,
                                    pipeline)
        self.jenkins = jenkins
        self.build_number = build_number
        self.jobname = jobname
        self.jenkins = jenkins
        self.yaml_dict = yaml_dict
        self.cli = cli
        self.pipeline = pipeline
        self.prev = prev

        self.still_running = False
        if not self.cli.offline_mode:
            self.fetch_data_if_appropriate(jenkins, jobname, build_number)
        self.process_job_data()

    def fetch_data_if_appropriate(self, jenkins, jobname, build_number):
        """ Pull console and artifacts from jenkins """
        path = os.path.join(self.cli.reportdir, jobname, build_number)
        if self.cli.dont_replace:
            if not os.path.exists(path):
                self.still_running = (jenkins.get_triage_data(build_number,
                                      jobname, self.cli.reportdir))
                if self.still_running:
                    self.cli.LOG.info("{} is still running - skipping"
                                      .format(path))
                else:
                    self.cli.LOG.info("{} (re)downloaded".format(path))
        else:
            self.still_running = jenkins.\
                get_triage_data(build_number, jobname, self.cli.reportdir)

    def process_job_data(self):
        self.message = 1
        if self.still_running:
            return
        path = \
            os.path.join(self.cli.reportdir, self.jobname, self.build_number)
        file_parser = FileParser(path=path, job=self.jobname)
        for err in file_parser.status:
            self.cli.LOG.error(err)

        matching_bugs = self.oil_survey(path, self.pipeline,
                                        file_parser.extracted_info)
        self.yaml_dict = self.add_to_yaml(matching_bugs, self.yaml_dict)
        self.message = 0
