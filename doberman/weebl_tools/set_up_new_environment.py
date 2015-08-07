import requests
import json
import subprocess
from weebl_specific_crude_cli import CLI
from doberman.common.common import Common
from doberman.analysis.crude_jenkins import Jenkins


class SetUpNewEnvironment(Common):

    def __init__(self, cli=False):
        self.cli = CLI().populate_cli() if not cli else cli
        self.headers = {"content-type": "application/json"}
        self.jenkins = Jenkins(self.cli)
        self.weeblify_environment()

    def weeblify_environment(self):
        self.set_up_new_environment()
        self.set_up_new_jenkins()
        self.set_up_new_build_executors()

    def get_internal_url_of_this_machine(self):
        return subprocess.check_output(["hostname", "-I"]).split()[0]

    def set_up_new_environment(self):
        url = "{}/api/v1/environment/".format(self.cli.weebl_ip)
        data = {'name': self.cli.environment}
        response = requests.post(url,
                                 headers=self.headers,
                                 data=json.dumps(data),
                                 auth=self.cli.weebl_auth)
        self.env_uuid = json.loads(response.text)['uuid']
        print("set up new {} environment: {}".format(self.cli.environment,
                                                     self.env_uuid))

    def set_up_new_jenkins(self):
        url = "{}/api/v1/jenkins/".format(self.cli.weebl_ip)
        data = {'environment': self.env_uuid,
                #'internal_access_url': self.get_internal_url_of_this_machine(),
                'external_access_url': self.cli.external_jenkins_url}
        response = requests.post(url,
                                 headers=self.headers,
                                 data=json.dumps(data),
                                 auth=self.cli.weebl_auth)
        print("set up new jenkins: {}".format(self.env_uuid))

    def set_up_new_build_executors(self):
        url = "{}/api/v1/build_executor/".format(self.cli.weebl_ip)
        self.jenkins.connect_to_jenkins()
        jkns = self.jenkins.jenkins_api
        for build_executor in jkns.get_nodes().iteritems():
            name = build_executor[0]
            data = {'name': name,
                    'jenkins': self.env_uuid}
            response = requests.post(url,
                                     headers=self.headers,
                                     data=json.dumps(data),
                                     auth=self.cli.weebl_auth)
            print("set up new build executor: {}".format(name))


if __name__ == "__main__":
    SetUpNewEnvironment()
