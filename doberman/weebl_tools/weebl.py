import json
import requests
import subprocess
from weebl_specific_crude_cli import CLI
from doberman.common.base import DobermanBase
from doberman.common.exception import UnexpectedStatusCode


class Weebl(DobermanBase):
    """Weebl API wrapper class."""

    def __init__(self, cli=False, report=True):
        self.cli = CLI().populate_cli() if not cli else cli
        self.headers = {"content-type": "application/json",
                        "limit": None}
        self.base_url = "{}/api/{}".format(self.cli.weebl_ip,
                                           self.cli.weebl_api_ver)

    def make_request(self, method, raise_exception=True, **params):
        params['headers'] = self.headers
        params['auth'] = self.cli.weebl_auth
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

    def weeblify_environment(self, ci_server_api=None, report=True):
        self.set_up_new_environment(report=report)
        self.set_up_new_jenkins(report=report)
        if ci_server_api is not None:
            self.set_up_new_build_executors(ci_server_api)

    def environment_existence_check(self, uuid):
        environment_instances = self.get_instances("environment")
        if uuid in [env.get('uuid') for env in environment_instances]:
            return True
        return False

    def build_existence_check(self, name, env_uuid):
        build_executor_instances = self.get_instances("build_executor")
        b_ex_in_env = [bex.get('name') for bex in build_executor_instances
                       if env_uuid in bex['jenkins']]
        return True if name in b_ex_in_env else False

    def jenkins_existence_check(self):
        jkns_instances = self.get_instances("jenkins")
        if jkns_instances is not None:
            if self.cli.uuid in [jkns.get('uuid') for jkns in jkns_instances]:
                return True
        return False

    def pipeline_existence_check(self, pipeline_id):
        pipeline_instances = self.get_instances("pipeline")
        if pipeline_instances is not None:
            if pipeline_id in [pl.get('uuid') for pl in pipeline_instances]:
                return True
        return False

    def set_up_new_build_executors(self, ci_server_api):
        newly_created_build_executors = []

        for build_executor in ci_server_api.get_nodes().iteritems():
            name = build_executor[0]
            if self.build_existence_check(name, self.env_uuid):
                continue

            # Create this build executor for this environment:
            url = "{}/build_executor/".format(self.base_url)
            data = {'name': name,
                    'jenkins': self.env_uuid}
            self.make_request('post', url=url, data=json.dumps(data))
            newly_created_build_executors.append(name)
        if newly_created_build_executors != []:
            msg = "Created the following {} environment build executor(s):\n{}"
            self.cli.LOG.info(msg.format(self.env_name,
                                         newly_created_build_executors))

    def set_up_new_environment(self, report=True):
        if self.environment_existence_check(self.cli.uuid):
            if report:
                self.cli.LOG.info("Environment exists with UUID: {}"
                                  .format(self.cli.uuid))
            self.env_uuid = self.cli.uuid
            self.env_name = self.cli.environment
            return

        # Create new environment:
        url = "{}/environment/".format(self.base_url)
        data = {'name': self.cli.environment,
                'uuid': self.cli.uuid}
        response = self.make_request('post', url=url, data=json.dumps(data))
        self.env_uuid = json.loads(response.text)['uuid']
        self.env_name = json.loads(response.text)['name']
        self.cli.LOG.info("Set up new {} environment: {}".format(
            self.cli.environment, self.env_uuid))

    def set_up_new_jenkins(self, report=True):
        if self.jenkins_existence_check():
            if report:
                self.cli.LOG.info("Jenkins exists with UUID: {}"
                                  .format(self.cli.uuid))
            return

        # Create new jenkins:
        url = "{}/jenkins/".format(self.base_url)
        data = {'environment': self.env_uuid,
                'external_access_url': self.cli.jenkins_host}
        # TODO: Add internal_access_url once it's reimplemented in the API:
        # data['internal_access_url'] = self.get_internal_url_of_this_machine()
        self.make_request('post', url=url, data=json.dumps(data))
        self.cli.LOG.info("Set up new jenkins: {}".format(self.cli.uuid))

    def check_in_to_jenkins(self, ci_server_api):
        url = "{}/jenkins/{}/".format(self.base_url, self.env_uuid)
        response = self.make_request('put', url=url)
        return json.loads(response.text).get('uuid')

    def create_pipeline(self, pipeline_id, build_executor_name):
        if self.pipeline_existence_check(pipeline_id):
            return pipeline_id

        # Get Build Executor:
        build_executor = self.get_build_executor_uuid_from_name(
            build_executor_name)

        # Create pipeline:
        url = "{}/pipeline/".format(self.base_url)
        data = {'build_executor': build_executor,
                'pipeline': pipeline_id}
        response = self.make_request('post', url=url, data=json.dumps(data))
        self.cli.LOG.info("Pipeline {} successfully created in Weebl db"
                          .format(pipeline_id))
        returned_pipeline = json.loads(response.text).get('uuid')

        # Error if pipelines do not match:
        if returned_pipeline != pipeline_id:
            msg = ("Pipeline created on weebl does not match: {} != {}"
                   .format(pipeline_id, self.pipeline))
            self.cli.LOG.error(msg)
            raise Exception(msg)

        return returned_pipeline

    def get_env_uuid_from_name(self, name):
        url = "{}/environment/by_name/{}/".format(self.base_url, name)
        response = self.make_request('get', url=url)
        return json.loads(response.text).get('uuid')

    def get_build_executor_uuid_from_name(self, build_executor_name):
        env_uuid = self.get_env_uuid_from_name(self.cli.environment)
        url = "{}/build_executor/".format(self.base_url)
        url_with_args = "{}?jenkins={}&name={}".format(url, env_uuid,
                                                       build_executor_name)
        response = self.make_request('get', url=url_with_args)
        objects = json.loads(response.text)['objects']

        if objects == []:
            return
        else:
            return objects[0].get('uuid')

    def get_internal_url_of_this_machine(self):
        return subprocess.check_output(["hostname", "-I"]).split()[0]
