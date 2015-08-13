import json
import requests
from doberman.common.common import Common


class Weebl(Common):
    """Weebl API wrapper class."""

    def __init__(self, cli=False, ci_server_api=None):
        self.cli = CLI().populate_cli() if not cli else cli
        self.headers = {"content-type": "application/json"}
        self.base_url = "{}/api/{}".format(self.cli.weebl_ip,
                                           self.cli.weebl_api_ver)
        self.weeblify_environment(ci_server_api)


    def get(self, url, expected_st_code):
        response = requests.get(url,
                                headers=self.headers,
                                auth=self.cli.weebl_auth)
        success = True if response.status_code == expected_st_code else False
        return success, response


    def post(self, url, data, expected_st_code):
        response = requests.post(url,
                                 headers=self.headers,
                                 data=json.dumps(data),
                                 auth=self.cli.weebl_auth)
        success = True if response.status_code == expected_st_code else False
        return success, response


    def put(self, url, data, expected_st_code):
        response = requests.put(url,
                                headers=self.headers,
                                data=json.dumps(data),
                                auth=self.cli.weebl_auth)
        success = True if response.status_code == expected_st_code else False
        return success, response


    def delete(self, url, expected_st_code):
        response = requests.delete(url,
                                   headers=self.headers,
                                   auth=self.cli.weebl_auth)
        success = True if response.status_code == expected_st_code else False
        return success, response


    def get_instances(self, obj, expected=200):
        url = "{}/{}/".format(self.base_url, obj)
        successful, response = self.get(url, expected)
        if not successful:
            self.unexpected(response.status_code, expected, response.text)
        return json.loads(response.text).get('objects')


    def unexpected(self, status_code, expected, rtext):
        msg = "Request returned a status code of {}, not {}:\n\n {}\n"
        raise Exception(msg.format(status_code, expected, rtext))


    def create_pipeline(self, pipeline_id, build_executor_name, expected=201):
        url = "{}/pipeline/".format(self.base_url)
        build_executor = self.get_build_executor_uuid_from_name(
            build_executor_name)
        data = {'build_executor': build_executor}
        successful, response = self.post(url, data, expected)
        if not successful:
            self.unexpected(response.status_code, expected, response.text)
        return json.loads(response.text).get('uuid')


    def get_env_uuid_from_name(self, name, expected=200):
        url = "{}/environment/by_name/{}/".format(self.base_url, name)
        successful, response = self.get(url, expected)
        if not successful:
            self.unexpected(response.status_code, expected, response.text)
        return json.loads(response.text).get('uuid')


    def get_build_executor_uuid_from_name(self, build_executor_name, expected=200):
        env_uuid = self.get_env_uuid_from_name(self.cli.environment)
        url = "{}/build_executor/".format(self.base_url)
        url_with_args = "{}?jenkins={}&name={}".format(url, env_uuid,
                                                       build_executor_name)
        successful, response = self.get(url_with_args, expected)
        if not successful:
            self.unexpected(response.status_code, expected, response.text)
        objects = json.loads(response.text)['objects']

        if objects == []:
            return
        else:
            return objects[0].get('uuid')


    def get_internal_url_of_this_machine(self):
        return subprocess.check_output(["hostname", "-I"]).split()[0]


    def weeblify_environment(self, ci_server_api):
        self.set_up_new_environment()
        self.set_up_new_jenkins()
        self.set_up_new_build_executors(ci_server_api)

    def set_up_new_environment(self, expected=201):
        # Check to see if environment already exists:
        environment_instances = self.get_instances("environment")
        if self.cli.uuid in [env.get('uuid') for env in environment_instances]:
            self.cli.LOG.info("Environment exists with UUID: {}"
                              .format(self.cli.uuid))
            self.env_uuid = self.cli.uuid
            self.env_name = self.cli.environment
            return

        # Create new environment:
        url = "{}/environment/".format(self.base_url)
        data = {'name': self.cli.environment,
                'uuid': self.cli.uuid}
        successful, response = self.post(url, data, expected)
        if not successful:
            self.unexpected(response.status_code, expected, response.text)
        self.env_uuid = json.loads(response.text)['uuid']
        self.env_name = json.loads(response.text)['name']
        self.cli.LOG.info("Set up new {} environment: {}".format(
            self.cli.environment, self.env_uuid))


    def set_up_new_jenkins(self, expected=201):
        # Check to see if jenkins already exists:
        jkns_instances = self.get_instances("jenkins")
        if jkns_instances is not None:
            if self.cli.uuid in [jkns.get('uuid') for jkns in jkns_instances]:
                self.cli.LOG.info("Jenkins exists with UUID: {}"
                              .format(self.cli.uuid))
                return

        # Create new jenkins:
        url = "{}/jenkins/".format(self.base_url)
        data = {'environment': self.env_uuid,
                #'internal_access_url': self.get_internal_url_of_this_machine(),
                'external_access_url': self.cli.external_jenkins_url}
        successful, response = self.post(url, data, expected)
        if not successful:
            self.unexpected(response.status_code, expected, response.text)
        self.cli.LOG.info("Set up new jenkins: {}".format(self.cli.uuid))


    def set_up_new_build_executors(self, ci_server_api, expected=201):
        build_executor_instances = self.get_instances("build_executor")
        newly_created_build_executors = []
        for build_executor in ci_server_api.get_nodes().iteritems():
            name = build_executor[0]
            # Check to see if this build_executor already exists:
            b_ex_in_env = [bex.get('name') for bex in build_executor_instances
                           if self.env_uuid in bex['jenkins']]
            if name in b_ex_in_env:
                continue

            # Create this build executor for this environment:
            url = "{}/build_executor/".format(self.base_url)
            data = {'name': name,
                    'jenkins': self.env_uuid}
            successful, response = self.post(url, data, expected)
            if not successful:
                self.unexpected(response.status_code, expected, response.text)
            newly_created_build_executors.append(name)
        if newly_created_build_executors != []:
            msg = "Created the following {} environment build executor(s):\n{}"
            self.cli.LOG.info(msg.format(self.env_name,
                                         newly_created_build_executors))


    def check_in_to_jenkins(self, ci_server_api, expected=200):
        url = "{}/jenkins/{}/".format(self.base_url, self.env_uuid)
        successful, response = self.put(url, expected)
        if not successful:
            self.unexpected(response.status_code, expected, response.text)
        return json.loads(response.text).get('uuid')
