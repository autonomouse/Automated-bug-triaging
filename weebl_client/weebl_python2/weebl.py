import json
import requests
import subprocess
from weebl_client.weebl_python2 import utils
from weebl_client.weebl_python2.exception import UnexpectedStatusCode


class Weebl(object):
    """Weebl API wrapper class."""

    def __init__(self, uuid, env_name,
                 #weebl_ip="http://10.245.0.14",     #  <-      LOOK HERE!!!
                 weebl_ip="http://localhost:8000",
                 weebl_api_ver="v1",
                 weebl_auth=('weebl', 'passweebl')):
        self.LOG = utils.get_logger("weeblSDK_python2")
        self.env_name = env_name
        self.uuid = uuid
        self.weebl_ip = weebl_ip
        self.weebl_auth = weebl_auth
        self.headers = {"content-type": "application/json",
                        "limit": None}
        self.base_url = "{}/api/{}".format(weebl_ip, weebl_api_ver)

    def make_request(self, method, raise_exception=True, **params):
        params['headers'] = self.headers
        params['auth'] = self.weebl_auth
        if method == 'get':
            response = requests.get(**params)
        elif method == 'post':
            response = requests.post(**params)
        elif method == 'put':
            response = requests.put(**params)
        elif method == 'delete':
            response = requests.delete(**params)
        # If response code isn't 2xx:
        if str(response.status_code)[0] != '2':
            msg = "Request returned a status code of {}:\n\n {}\n"
            if raise_exception:
                raise UnexpectedStatusCode(
                    msg.format(response.status_code, response.text))
        return response

    def get_instances(self, obj):
        url = "{}/{}/".format(self.base_url, obj)
        response = self.make_request('get', url=url)
        return json.loads(response.text).get('objects')

    def get_single_instance(self, obj, instance_id):
        url = "{}/{}/{}/".format(self.base_url, obj, instance_id)
        response = self.make_request('get', url=url)
        return json.loads(response.text)

    def weeblify_environment(self, jenkins_host, ci_server_api=None,
                             report=True):
        self.set_up_new_environment(report=report)
        self.set_up_new_jenkins(jenkins_host, report=report)
        if ci_server_api is not None and hasattr(ci_server_api, 'jenkins_api'):
            self.set_up_new_build_executors(ci_server_api.jenkins_api)

    def environment_exists(self, uuid):
        environment_instances = self.get_instances("environment")
        if uuid in [env.get('uuid') for env in environment_instances]:
            return True
        return False

    def build_executor_exists(self, name, env_uuid):
        build_executor_instances = self.get_instances("build_executor")
        b_ex_in_env = [bex.get('name') for bex in build_executor_instances
                       if env_uuid in bex['jenkins']]
        return True if name in b_ex_in_env else False

    def jenkins_exists(self):
        jkns_instances = self.get_instances("jenkins")
        if jkns_instances is not None:
            if self.uuid in [jkns.get('uuid') for jkns in jkns_instances]:
                return True
        return False

    def pipeline_exists(self, pipeline_id):
        pipeline_instances = self.get_instances("pipeline")
        if pipeline_instances is not None:
            if pipeline_id in [pl.get('uuid') for pl in pipeline_instances]:
                return True
        return False

    def build_exists(self, build_id, job_type, pipeline):
        build_instances = self.get_instances("build")
        builds = [bld.get('build_id') for bld in build_instances if pipeline
                  in bld['pipeline'] and job_type in bld['job_type']]
        return True if build_id in builds else False

    def regular_expression_exists(self, regex):
        regular_expression_instances = self.get_instances("regular_expression")
        if regular_expression_instances is not None:
            if regex in [kbr.get('regex') for kbr in
                         regular_expression_instances]:
                return True
        return False

    def target_file_glob_exists(self, glob_pattern):
        target_file_glob_instances = self.get_instances("target_file_glob")
        if target_file_glob_instances is not None:
            if glob_pattern in [tfglobs.get('glob_pattern') for tfglobs in
                                target_file_glob_instances]:
                return True
        return False

    def set_up_new_build_executors(self, ci_server_api):
        newly_created_build_executors = []

        for build_executor in ci_server_api.get_nodes().iteritems():
            name = build_executor[0]
            if self.build_executor_exists(name, self.uuid):
                continue

            # Create this build executor for this environment:
            url = "{}/build_executor/".format(self.base_url)
            data = {'name': name,
                    'jenkins': self.uuid}
            self.make_request('post', url=url, data=json.dumps(data))
            newly_created_build_executors.append(name)
        if newly_created_build_executors != []:
            msg = "Created the following {} environment build executor(s):\n{}"
            self.LOG.info(msg.format(self.env_name,
                          newly_created_build_executors))

    def set_up_new_environment(self, report=True):
        if self.environment_exists(self.uuid):
            if report:
                self.LOG.info("Environment exists with UUID: {}"
                              .format(self.uuid))
            env_name = self.get_env_name_from_uuid(self.uuid)
            if env_name != self.env_name:
                msg = "Environment name provided ({0}) does not match the "
                msg += "name of the environment with uuid: {1}, which is {2}. "
                msg += "Using {2} as environment name instead."
                self.LOG.error(
                    msg.format(self.env_name, self.uuid, env_name))
                self.env_name = env_name
            return

        # Create new environment:
        url = "{}/environment/".format(self.base_url)
        data = {'name': self.env_name,
                'uuid': self.uuid}
        response = self.make_request('post', url=url, data=json.dumps(data))
        self.env_name = json.loads(response.text)['name']
        self.LOG.info("Set up new {} environment: {}".format(
            self.env_name, self.uuid))

    def set_up_new_jenkins(self, jenkins_host, report=True):
        if self.jenkins_exists():
            if report:
                self.LOG.info("Jenkins exists with UUID: {}"
                              .format(self.uuid))
            return

        # Create new jenkins:
        url = "{}/jenkins/".format(self.base_url)
        data = {'environment': self.uuid,
                'external_access_url': jenkins_host}
        # TODO: Add internal_access_url once it's reimplemented in the API:
        # data['internal_access_url'] = self.get_internal_url_of_this_machine()
        self.make_request('post', url=url, data=json.dumps(data))
        self.LOG.info("Set up new jenkins: {}".format(self.uuid))

    def check_in_to_jenkins(self, ci_server_api):
        url = "{}/jenkins/{}/".format(self.base_url, self.uuid)
        response = self.make_request('put', url=url)
        return json.loads(response.text).get('uuid')

    def create_pipeline(self, pipeline_id, build_executor_name):
        if self.pipeline_exists(pipeline_id):
            return pipeline_id

        # Get Build Executor:
        build_executor = self.get_build_executor_uuid_from_name(
            build_executor_name)

        # Create pipeline:
        url = "{}/pipeline/".format(self.base_url)
        data = {'build_executor': build_executor,
                'pipeline': pipeline_id}
        response = self.make_request('post', url=url, data=json.dumps(data))
        self.LOG.info("Pipeline {} successfully created in Weebl db"
                      .format(pipeline_id))
        returned_pipeline = json.loads(response.text).get('uuid')

        # Error if pipelines do not match:
        if returned_pipeline != pipeline_id:
            msg = ("Pipeline created on weebl does not match: {} != {}"
                   .format(pipeline_id, returned_pipeline))
            self.LOG.error(msg)
            raise Exception(msg)

        return returned_pipeline

    def create_regular_expression(self, glob_pattern, regex, bug=None):
        if self.regular_expression_exists(regex):
            return

        # Create regular_expression:
        url = "{}/regular_expression/".format(self.base_url)
        data = {"target_file_globs": glob_pattern,
                "regex": regex}
        if bug is not None:
            data['bug'] = bug
        response = self.make_request('post', url=url, data=json.dumps(data))
        returned_regex = json.loads(response.text).get('regular_expression')
        if response.status_code == 201:
            self.LOG.info(
                "Regex \"{}\" successfully created in Weebl".format(regex))
        else:
            msg = "Error submitting regex \"{}\" to Weebl".format(regex)
            self.LOG.error(msg)
            raise Exception(msg)

    def create_target_file_glob(self, glob_pattern, job_types=None):
        # Create target_file_glob:
        data = {"glob_pattern": glob_pattern}
        if job_types is not None:
            data["job_types"] = job_types
        if self.target_file_glob_exists(glob_pattern):
            url = "{}/target_file_glob/{}/".format(self.base_url, glob_pattern)
            response = self.make_request('put', url=url, data=json.dumps(data))
        else:
            url = "{}/target_file_glob/".format(self.base_url)
            response = self.make_request('post', url=url,
                                         data=json.dumps(data))
        returned_glob_pattern = json.loads(response.text).get('glob_pattern')

        # Error if glob_patterns do not match:
        if glob_pattern != returned_glob_pattern:
            msg = ("Glob_pattern created on weebl does not match: {} != {}"
                   .format(glob_pattern, returned_glob_pattern))
            self.LOG.error(msg)
            raise Exception(msg)
        if self.target_file_glob_exists(glob_pattern):
            msg = "TargetFileglob \"{}\" successfully updated with jobs(s): {}"
            job_type_list =\
                job_types if type(job_types) is list else [job_types]
            self.LOG.info(msg.format(glob_pattern, ",".join(job_type_list)))
        else:
            self.LOG.info("TargetFileglob \"{}\" successfully created"
                          .format(glob_pattern))

    def get_env_name_from_uuid(self, uuid):
        url = "{}/environment/{}/".format(self.base_url, uuid)
        response = self.make_request('get', url=url)
        return json.loads(response.text).get('name')

    def get_env_uuid_from_name(self, name):
        url = "{}/environment/by_name/{}/".format(self.base_url, name)
        response = self.make_request('get', url=url)
        return json.loads(response.text).get('uuid')

    def get_build_executor_uuid_from_name(self, build_executor_name):
        url = "{}/build_executor/".format(self.base_url)
        url_with_args = "{}?jenkins={}&name={}".format(url, self.uuid,
                                                       build_executor_name)
        response = self.make_request('get', url=url_with_args)
        objects = json.loads(response.text)['objects']

        if objects == []:
            return
        else:
            return objects[0].get('uuid')

    def get_internal_url_of_this_machine(self):
        return subprocess.check_output(["hostname", "-I"]).split()[0]

    def create_build(self, build_id, pipeline, job_type, build_status,
                     build_started_at=None, build_finished_at=None,
                     ts_format="%Y-%m-%d %H:%M:%SZ"):
        if self.build_exists(build_id, job_type, pipeline):
            return build_id

        # Create build:
        url = "{}/build/".format(self.base_url)
        data = {'build_id': build_id,
                'pipeline': pipeline,
                'build_status': build_status.lower(),
                'job_type': job_type}
        if build_started_at:
            data['build_started_at'] =\
                self.convert_timestamp_to_string(build_started_at, ts_format)
        if build_finished_at:
            data['build_finished_at'] =\
                self.convert_timestamp_to_string(build_finished_at, ts_format)
        response = self.make_request('post', url=url, data=json.dumps(data))
        build_uuid = json.loads(response.text).get('uuid')
        self.LOG.info("Build {} successfully created (build uuid: {})"
                      .format(build_id, build_uuid))

        returned_build_id = json.loads(response.text).get('build_id')

        # Error if builds do not match:
        if returned_build_id != build_id:
            msg = ("Build created on weebl does not match: {} != {}"
                   .format(build_id, self.build_number))
            self.LOG.error(msg)
            raise Exception(msg)

        return returned_build_id

    def populate_re_dict(self, regular_expression):
        re_dict = {}
        regex = {'regexp': [regular_expression['regex']]}
        for target_file_glob in regular_expression['target_file_globs']:
            tfglobs = [(tfile['job_types'], tfile['glob_pattern']) for tfile in
                       self.get_instances("target_file_glob") if
                       tfile['glob_pattern'] == target_file_glob]
            #if tfglobs == []:
            #    re_dict['*']['*'] = regex
            for jobs, glob_pattern in tfglobs:
                for job in jobs:
                    if not hasattr(re_dict, 'job'):
                        re_dict[job] = []
                    re_dict[job].append({glob_pattern: regex})
        return re_dict

    def get_bug_info(self, force_refresh=True):
        self.LOG.info("Downloading bug regexs from Weebl: {}"
                      .format(self.weebl_ip))
        known_bug_regex_instances = self.get_instances("known_bug_regex")
        bug_instances = self.get_instances("bug")
        bug_tracker_bug_instances = self.get_instances("bug_tracker_bug")
        target_file_glob = self.get_instances("target_file_glob")
        return self.munge_bug_info_data(
            known_bug_regex_instances, bug_instances,
            bug_tracker_bug_instances, target_file_glob)


    def munge_bug_info_data(self, known_bug_regex_instances, bug_instances,
                            bug_tracker_bug_instances, target_file_globs):
        """Get the data and put it into the format doberman is expecting (the
        same as test-catalog's get_bug_info method).
        """

        bug_info = {'bugs': {}}
        for target_file_glob in target_file_globs:
            tfile = target_file_glob['glob_pattern']
            jobs = target_file_glob.get('job_types')
            if jobs == []:
                continue
            for known_bug_regex in known_bug_regex_instances:
                regex = known_bug_regex['regex']
                regex_uuid = known_bug_regex['uuid']
                files_bug_affects = known_bug_regex.get('target_file_globs')
                weebl_bug = known_bug_regex.get('bug')

                for bug in bug_instances:
                    # Description here is misnamed - actually means summary:
                    description = bug.get('summary')
                    if bug['uuid'] == weebl_bug:
                        if bug['bug_tracker_bugs'] == []:
                            continue
                        lp_bugs = bug['bug_tracker_bugs']

                        if tfile in files_bug_affects:
                            for job in jobs:
                                tfile_regex = {}
                                for lp_bug in lp_bugs:
                                    if lp_bug not in bug_info['bugs']:
                                        bug_info['bugs'][lp_bug] = {}

                                    if 'affects' not in bug_info['bugs'][lp_bug]:
                                        bug_info['bugs'][lp_bug]['affects'] = []  # TODO: Get from bug_tracker_bug after LP integration
                                    if 'category' not in bug_info['bugs'][lp_bug]:
                                        bug_info['bugs'][lp_bug]['category'] = []  # TODO: Get from bug_tracker_bug after LP integration
                                    if 'description' not in bug_info['bugs'][lp_bug]:
                                        bug_info['bugs'][lp_bug]['description'] = description
                                    if 'regex_uuid' not in bug_info['bugs'][lp_bug]:
                                        bug_info['bugs'][lp_bug]['regex_uuid'] = regex_uuid
                                    if job not in bug_info['bugs'][lp_bug]:
                                        bug_info['bugs'][lp_bug][job] = []

                                    if tfile not in tfile_regex:
                                        tfile_regex[tfile] = {'regexp': []}
                                    if regex not in tfile_regex[tfile]['regexp']:
                                        tfile_regex[tfile]['regexp'].append(regex)
                                bug_info['bugs'][lp_bug][job].append(tfile_regex)

        return bug_info

    def delete_bug_info(self, bugno):
        """This method does nothing, as deletion is not required for updating
        the data in weebl."""
        pass

    def add_bug_info(self, bugno, job_types, glob_pattern, regex, boolean):
        """
        warning:
        'Failed to parse config:\s+lxc.include\s+=\s+.usr.share.lxc.config.ubuntu-cloud.common.conf'
        has become:
        'Failed to parse config:\\s+lxc.include\\s+=\\s+.usr.share.lxc.config.ubuntu-cloud.common.conf'

        check in doberman once it is downloaded again
        """
        self.create_target_file_glob(
            glob_pattern=glob_pattern, job_types=job_types)
        self.create_known_bug_regex(
            glob_pattern=glob_pattern, regex=regex, bug=bugno)
