import json
import requests
from doberman.common.common import Common


class Weebl(Common):
    """Weebl API wrapper class."""

    def __init__(self, cli):
        self.cli = cli

    def create_pipeline(self, pipeline_id, build_executor_name):
        url = "{}/api/v1/pipeline/".format(self.cli.weebl_ip)
        build_executor = self.get_build_executor_uuid_from_name(
            build_executor_name)
        data = {'build_executor': build_executor}
        response = requests.post(url,
                                 headers={"content-type":"application/json"},
                                 data=json.dumps(data),
                                 auth=self.cli.weebl_auth)
        return json.loads(response.text).get('uuid')
        

    def get_env_uuid_from_name(self, name):
        url = "{}/api/v1/environment/by_name/{}/".format(self.cli.weebl_ip,
                                                         name)
        response = requests.get(url,
                                headers={"content-type":"application/json"},
                                auth=self.cli.weebl_auth)
        return json.loads(response.text).get('uuid')

    def get_build_executor_uuid_from_name(self, build_executor_name):
        env_uuid = self.get_env_uuid_from_name(self.cli.environment)
        url = "{}/api/v1/build_executor/".format(self.cli.weebl_ip)
        url_with_args = "{}?jenkins={}&name={}".format(url, env_uuid,
                                                       build_executor_name)
        response = requests.get(url_with_args,
                                headers={"content-type":"application/json"},
                                auth=self.cli.weebl_auth)
        objects = json.loads(response.text)['objects']
        
        if objects == []:
            return 
        else:
            return objects[0].get('uuid')
