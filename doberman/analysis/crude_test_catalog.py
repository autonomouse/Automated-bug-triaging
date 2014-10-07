
from crude_common import Common

import sys
import os
import re
import yaml
import socket
import urlparse
import tarfile
import shutil
import uuid
import optparse
import datetime
import json
from test_catalog.client.api import TCClient
from test_catalog.client.base import TCCTestPipeline
from pandas import DataFrame
from lxml import etree
from jenkinsapi.jenkins import Jenkins as JenkinsAPI
from doberman.common import pycookiecheat, utils
from jenkinsapi.custom_exceptions import *

LOG = utils.get_logger('doberman.analysis')
            
class TestCatalog(Common):
    """            
    """
    
    def __init__(self, cli):
        
        self.cli = cli
        self.cookie = self.cli.tc_auth
        self.tc_client = TCClient
        self._tc_client = []
        self.get_tc_client()
        self.open_bug_database()  # Connect to bugs DB

    def open_bug_database(self):
        if self.cli.database in [None, 'None', 'none', '']:
            LOG.info("Connecting to test-catalog bug/regex database")
            self.b = self.client.get_bug_info(force_refresh=True)            
        elif len(self.cli.database):
            LOG.info("Connecting to database file: %s" % (self.cli.database))
            with open(self.cli.database, "r") as mock_db_file:
                self.bugs = yaml.load(mock_db_file)['bugs']
        else:
            LOG.error('Unknown database: %s' % (self.cli.database))
            raise Exception('Invalid Database configuration')

    def get_tc_client(self):
        if self._tc_client and not self.cli.tc_host:
            self.client = self._tc_client[0]
        self.connect_to_testcatalog()
        self._tc_client.append(self.client)
    
    def connect_to_testcatalog(self):
        LOG.debug('Connecting to test-catalog @ %s remote=%s'
                  % (self.cli.tc_host, self.cli.run_remote))
        if self.cookie is None:
            LOG.info("Fetching test-catalog cookies for %s" % self.cli.tc_host)
            self.cookie = pycookiecheat.chrome_cookies(self.cli.tc_host)
        LOG.info("Fetching test-catalog using endpoint=%s" % self.cli.tc_host)
        self.client = self.tc_client(endpoint=self.cli.tc_host,
                                     cookies=self.cookie)

    def get_pipelines(self, pipeline):
        """ Using test-catalog, return the build numbers for the jobs that are
            part of the given pipeline.

        """
        LOG.info('Fetching data on pipeline: %s' % (pipeline))        
        try:
            pl_tcat = TCCTestPipeline(self.client, pipeline)
        except Exception, e:
            msg = "test-catalog error. Does pipeline exist? Is there a cookie-"
            msg += "related issue? (%s)" % e
            LOG.error(msg)
            raise Exception(msg)
        try:
            deploy_dict = pl_tcat.dict['parent']
            deploy_build = deploy_dict['build_tag'].split("-")[-1]
        except:
            deploy_build = None
        try:
            prepare_dict = deploy_dict['children'][0]
            prepare_build = prepare_dict['build_tag'].split("-")[-1]
        except:
            prepare_build = None
        try:
            tempest_dict = prepare_dict['children'][0]
            tempest_build = tempest_dict['build_tag'].split("-")[-1]
        except:
            tempest_build = None

        return (deploy_build, prepare_build, tempest_build)
        
    def pipeline_check(self, pipeline_id):
        return [8, 4, 4, 4, 12] == [len(x) for x in pipeline_id.split('-')] 
