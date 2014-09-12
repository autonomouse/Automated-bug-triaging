#! /usr/bin/env python2

import sys
import os
import re
import yaml
import pandas as pd
import socket
import urlparse
import tarfile
import shutil
import uuid
import optparse
from test_catalog.client.api import TCClient as tc_client
from test_catalog.client.base import TCCTestPipeline
from pandas import DataFrame, Series
from lxml import etree
from jenkinsapi.jenkins import Jenkins
from jenkinsapi.custom_exceptions import *
from doberman.common import pycookiecheat, utils

LOG = utils.get_logger('doberman.analysis')
_tc_client = []
_jenkins = []


def get_jenkins(url, remote=False):
    if _jenkins and not url:
        return _jenkins[0]

    jenkins = connect_to_jenkins(url, remote)
    _jenkins.append(jenkins)
    return jenkins


def get_tc_client(api, remote=False):
    if _tc_client and not api:
        return _tc_client[0]

    tc_client = connect_to_testcatalog(api, remote)
    _tc_client.append(tc_client)
    return tc_client


def connect_to_testcatalog(api, remote=False):
    LOG.debug('Connecting to test-catalog @ %s remote=%s' % (api, remote))
    if remote:
        LOG.info("Fetching cookies for %s" % api)
        cookies = pycookiecheat.chrome_cookies(api)
        return tc_client(endpoint=api, cookies=cookies)
    else:  # If no auth_file, then assume running on jenkins
        return tc_client(endpoint=api)


def connect_to_jenkins(url, remote=False):
    """ Connects to jenkins via jenkinsapi, returns a jenkins object. """

    LOG.debug('Connecting to jenkins @ %s remote=%s' % (url, remote))
    netloc = socket.gethostbyname(urlparse.urlsplit(url).netloc)
    cookies = None

    if remote:
        LOG.info("Fetching cookies for %s" % url)
        cookies = pycookiecheat.chrome_cookies(url)
    try:
        return Jenkins(baseurl=url, cookies=cookies, netloc=netloc)
    except JenkinsAPIException:
        LOG.exception('Failed to connect to Jenkins')


def get_pipelines(pipeline, api, remote=False):
    """ Using test-catalog, return the build numbers for the jobs that are
        part of the given pipeline.

    """
    LOG.info('Fetching data on pipeline: %s' % (pipeline))
    client = get_tc_client(api, remote)
    pl_tcat = TCCTestPipeline(client, pipeline)
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


def get_triage_data(jenkins, build_num, job, reportdir):
    """ Get the artifacts from jenkins via jenkinsapi object. """
    jenkins_job = jenkins[job]
    build = jenkins_job.get_build(int(build_num))
    outdir = os.path.join(reportdir, job, str(build_num))
    LOG.info('Downloading debug data to: %s' % (outdir))
    try:
        os.makedirs(outdir)
    except OSError:
        if not os.path.isdir(outdir):
            raise
    with open(os.path.join(outdir, "console.txt"), "w") as cnsl:
        LOG.info('Saving console @ %s to %s' % (build.baseurl, outdir))
        console = build.get_console()
        cnsl.write(console)
        cnsl.write('\n')
        cnsl.flush()

    for artifact in build.get_artifacts():
        artifact.save_to_dir(outdir)
        extract_and_delete_archive(outdir, artifact)


def extract_and_delete_archive(outdir, artifact):
    """ Extracts the contents of a tarball and places it into a new file
        of the samename without the .tar.gz suffix (N.B. this leaves
        .ring.gz intact as they seem to contain binary ring files that
        I'm not sure what to do with at this point).

    """
    try:
        if 'tar.gz' in artifact.filename:
            path_to_artifact = os.path.join(outdir, artifact.filename)
            with tarfile.open(path_to_artifact, 'r:gz') as tar:
                tarlist = \
                    [member for member in tar.getmembers() if member.isfile()]
                for compressed_file in tarlist:
                    slug = compressed_file.name.replace('/', '_')
                    with open(os.path.join(outdir, slug), 'w') as new_file:
                        data = tar.extractfile(compressed_file).readlines()
                        new_file.writelines(data)
            os.remove(os.path.join(outdir, artifact.filename))
    except:
        LOG.error("Could not extract %s" % artifact.filename)


def process_deploy_data(pline, deploy_build, jenkins, reportdir, bugs,
                        yaml_dict, xmls):
    """ Parses the artifacts files from a single pipeline into data and
        metadata DataFrames

    """
    pipeline_deploy_path = os.path.join(reportdir, 'pipeline_deploy',
                                        deploy_build)

    # Get paths of data files:
    oil_node_location = os.path.join(pipeline_deploy_path, 'oil_nodes')
    juju_status_location = os.path.join(pipeline_deploy_path,
                                        'juju_status.yaml')
    pipeline_status_location = os.path.join(pipeline_deploy_path,
                                            'pipeline_status')
    mapping_location = os.path.join(pipeline_deploy_path, 'mapping.json')

    # Get vendor mapping:
    with open(mapping_location, "r") as mapping_file:
        vendor_mapping = yaml.load(mapping_file)

    # Read oil nodes file:
    with open(oil_node_location, "r") as nodes_file:
        oil_nodes = DataFrame(yaml.load(nodes_file)['oil_nodes'])
        oil_nodes.rename(columns={'host': 'node'}, inplace=True)

    # Read juju status file:
    with open(juju_status_location, "r") as jjstat_file:
        juju_status = yaml.load(jjstat_file)

    # Put machines data into a pandas DataFrame:
    machines = DataFrame(juju_status['machines']).T  # transpose
    machines.index.name = 'machine'
    machines.reset_index(level=0, inplace=True)
    machines.rename(columns={'dns-name': 'node'}, inplace=True)

    # Put service data into a pandas DataFrame (without relations/units)
    service = DataFrame(juju_status['services']).T  # transpose
    try:
        service.pop('relations')
    except:
        pass
    try:
        service.pop('units')
    except:
        pass
    service.index.name = 'service'
    service.reset_index(level=0, inplace=True)

    # Put relations and units data into pandas DataFrames:
    rel = {}
    unit = {}
    for serv in juju_status['services'].keys():
        try:
            rel[serv] = juju_status['services'][serv]['relations']
        except:
            pass
        try:
            units_dict = juju_status['services'][serv]['units']
            # Raise this services sub-dictionary to the top level:
            for key in units_dict.keys():
                unit[key] = juju_status['services'][serv]['units'][key]
        except:
            pass
    relations = DataFrame(rel).T  # transpose
    relations.index.name = 'service'
    relations.reset_index(level=0, inplace=True)

    units = DataFrame(unit).T  # transpose
    units.index.name = 'service'
    units.reset_index(level=0, inplace=True)
    try:
        units.pop('agent-state')
    except:
        pass
    try:
        units.pop('agent-version')
    except:
        pass

    # Merge units and relations DataFrames, using the service column:
    unit_and_rels = pd.merge(units, relations, how='outer')

    # Merge service & unit_and_rels DataFrames, using services column:
    services = pd.merge(service, unit_and_rels, how='outer')

    # Merge oil_nodes with machines, using node column:
    nodes = oil_nodes.merge(machines)

    # Merge nodes and services DataFrames, using the machine column:
    try:
        oil_df = pd.merge(nodes, services, how='outer')
        oil_df['machine'] = oil_df['machine'].dropna().astype('int')
        oil_df = oil_df.set_index('machine')
        oil_df.sort_index(inplace=True)
        vendor = {}
        for key in vendor_mapping.keys():
            vendor[key.replace('_', '-')] = vendor_mapping[key]
        oil_df['vendor'] = Series(vendor, index=oil_df['service']).values
    except:
        oil_df = DataFrame()
        oil_df['node'] = None
        oil_df['vendor'] = None
        oil_df['service'] = None

    # Get pipeline_status:
    with open(pipeline_status_location, "r") as pls_file:
        pipeline_status = pls_file.readlines()

    # Get metadata:
    metadata = {}
    metadata['environment'] = juju_status['environment']

    for line in pipeline_status:
        if not ("Pipeline Metadata" in line) and \
           re.sub(r'[^\w]', ' ', line).replace(' ', '') != '':
            if "Pipeline Jobs" in line:
                break
                # I could get the build_status from here, but I'm not sure
                # that I trust it, so I've used a jenkins poll instead, below
            else:
                split_line = line.lstrip('|').rstrip(' |\n').split('|')
                metadata[split_line[0].lstrip().rstrip()] = \
                    split_line[1].lstrip().rstrip()

    matching_bugs, build_status = \
        bug_hunt('pipeline_deploy', jenkins, deploy_build, bugs, oil_df,
                 pipeline_deploy_path, xmls)

    yaml_dict = add_to_yaml(pline, deploy_build, matching_bugs, build_status,
                            existing_dict=yaml_dict)

    return (oil_df, yaml_dict)


def process_prepare_data(pline, prepare_build, jenkins, reportdir, bugs,
                         oil_df, yaml_dict, xmls):
    """ Parses the artifacts files from a single pipeline into data and
        metadata DataFrames.

    """
    prepare_path = os.path.join(reportdir, 'pipeline_prepare',
                                prepare_build)
    matching_bugs, build_status = \
        bug_hunt('pipeline_prepare', jenkins, prepare_build, bugs, oil_df,
                 prepare_path, xmls)

    yaml_dict = add_to_yaml(pline, prepare_build, matching_bugs, build_status,
                            existing_dict=yaml_dict)
    return yaml_dict


def process_tempest_data(pline, tempest_build, jenkins, reportdir, bugs,
                         oil_df, yaml_dict, xmls):
    """
    Parses the artifacts files from a single pipeline into data and
    metadata DataFrames

    """
    tts_path = os.path.join(reportdir, 'test_tempest_smoke', tempest_build)

    matching_bugs, build_status = \
        bug_hunt('test_tempest_smoke', jenkins, tempest_build, bugs, oil_df,
                 tts_path, xmls)

    for xml_target_file in xmls:
        matching_bugs = xml_rematch(bugs, tts_path, xml_target_file,
                                    matching_bugs, 'test_tempest_smoke',
                                    build_status, oil_df)

    yaml_dict = add_to_yaml(pline, tempest_build, matching_bugs,
                            build_status, existing_dict=yaml_dict)
    return yaml_dict


def bug_hunt(job, jenkins, build, bugs, oil_df, path, ignore=[]):
    """ Searches provided text for each regexp from the bugs database. """
    build_status = [build_info for build_info in jenkins[job]._poll()['builds']
                    if build_info['number'] == int(build)][0]['result']
    matching_bugs = {}
    units_list = oil_df['service'].tolist()
    machines_list = oil_df['node'].tolist()
    vendors_list = oil_df['vendor'].tolist()
    bug_unmatched = True
    for bug_id in bugs.keys():
        if job in bugs[bug_id]:
            # Any of the dicts in bugs[bug_id][job] can match (or):
            OR_dict = bugs[bug_id][job]
            for AND_dict in OR_dict:
                # Within the dictionary all have to match (and):
                hit_list = []
                # Load up the file for each target_file in the DB for this bug:
                for target_file in AND_dict.keys():
                    target_location = os.path.join(path, target_file)
                    if not (target_file in ignore):
                        # TODO: raise error if no file (or make unfiled bug?)
                        with open(target_location, 'r') as grep_me:
                            text = grep_me.read()
                        hit_list = rematch(hit_list, AND_dict, target_file,
                                           text)

                if hit_list:
                    matching_bugs[bug_id] = {'regexp': hit_list,
                                             'vendors': vendors_list,
                                             'machines': machines_list,
                                             'units': units_list}
                    bug_unmatched = False
    if bug_unmatched and build_status == 'FAILURE':
        bid = 'unfiled-' + str(uuid.uuid4())
        matching_bugs[bid] = {'regexp': 'NO REGEX - UNFILED/UNMATCHED BUG',
                              'vendors': vendors_list,
                              'machines': machines_list,
                              'units': units_list}
    return (matching_bugs, build_status)


def rematch(hit_list, bugs, target_file, text):
    """ Search files in bugs for multiple matching regexps. """
    regexps = bugs[target_file]['regexp']
    if type(regexps) == list:
        if len(regexps) > 1:
            regexp = '|'.join(regexps)
        else:
            regexp = regexps[0]
        set_re = set(regexps)
    else:
        regexp = regexps
        set_re = set([regexps])
    if regexp not in ['None', None, '']:
        matches = re.compile(regexp, re.DOTALL).findall(text)
        # TODO: This checks that they match, but not that they do so in the
        # correct order yet:
        if set_re == set(matches):
            hit_list.append({target_file: regexps})
        else:
            hit_list = []
    return hit_list


def xml_rematch(bugs, path, xml_target_file, matching_bugs, job, build_status,
                oil_df):
    """ Search xml file for tests that return text containing regexps. """
    bug_unmatched = True
    units_list = oil_df['service'].tolist()
    machines_list = oil_df['node'].tolist()
    vendors_list = oil_df['vendor'].tolist()
    tempest_xml_location = os.path.join(path, xml_target_file)
    if os.path.isfile(tempest_xml_location):
        # Get tempest results:
        doc = etree.parse(tempest_xml_location).getroot()
        errors_and_fails = doc.xpath('.//failure') + doc.xpath('.//error')
        hit = []
        for num, fail in enumerate(errors_and_fails):
            pre_log = fail.get('message').split("begin captured logging")[0]
            # test = fail.getparent().attrib['classname'] + " - " + \
            #     fail.getparent().attrib['name']
            # failure_type = fail.get('type')
            earlier_matching_bugs = matching_bugs
            for bug in bugs:
                if job in bugs[bug]:
                    # TODO: multiple or just use [0]?
                    tempest_bug = bugs[bug][job][0]
                    # regexp = tempest_bug[xml_target_file]['regexp']
                    hit = rematch(hit, tempest_bug, xml_target_file,
                                  pre_log)
                    if hit:
                        matching_bugs[bug] = {'regexp': hit,
                                              'vendors': vendors_list,
                                              'machines': machines_list,
                                              'units': units_list}
                        bug_unmatched = False

                        # Merge matching_bugs dictionaries:
                        earlier_items = list(earlier_matching_bugs.items())
                        current_items = list(matching_bugs.items())
                        matching_bugs = dict(earlier_items + current_items)

    return (matching_bugs, bug_unmatched)


def add_to_yaml(pline, build, matching_bugs, build_status, existing_dict=None):
    """
    Creates a yaml dict and populates with data in the right format and merges
    with existing yaml dict.

    """
    # Make dict
    yaml_dict = {}
    if matching_bugs != {}:
        yaml_dict['pipeline'] = {pline: {'status': build_status,
                                         'build': build,
                                         'bugs': matching_bugs}}
    # Merge with existing dict:
    if existing_dict:
        yaml_dict = dict(list(existing_dict.items()) + list(yaml_dict.items()))

    return yaml_dict


def export_to_yaml(yaml_dict, job, reportdir):
    """ Write output files. """
    filename = 'triage_' + job + '.yml'
    file_path = os.path.join(reportdir, filename)
    with open(file_path, 'w') as outfile:
        outfile.write(yaml.safe_dump(yaml_dict, default_flow_style=False))
        LOG.info(filename + " written to " + reportdir)


def open_bug_database(database_uri, remote=False):
    if len(database_uri):
        if not database_uri.startswith("/"):
            filename = os.path.join(os.getcwd(), database_uri)

        LOG.info("Connecting to database file: %s" % (filename))
        with open(filename, "r") as mock_db_file:
            return yaml.load(mock_db_file)['bugs']
    elif database_uri in [None, 'None', 'none', '']:
        LOG.info("Connecting to test-catalog bug/regex database")
        client = get_tc_client(remote, database_uri)
        return client.get_bug_info(force_refresh=True)
    else:
        LOG.error('Unknown database: %s' % (database_uri))
        raise Exception('Invalid Database configuration')


def main():
    usage = "usage: %prog [options] pipeline_id1 pipeline_id2 ..."
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-c', '--config', action='store', dest='configfile',
                      default=None,
                      help='specify path to configuration file')
    parser.add_option('-d', '--dburi', action='store', dest='database',
                      default=None,
                      help='set URI to bug/regex db: /path/to/mock_db.yaml')
    parser.add_option('-J', '--jenkins', action='store', dest='jenkins_host',
                      default=None,
                      help='URL to Jenkins server')
    parser.add_option('-n', '--netloc', action='store', dest='netloc',
                      default=None,
                      help='Specify an IP to rewrite URLs')
    parser.add_option('-r', '--remote', action='store_true', dest='run_remote',
                      default=False,
                      help='set if running analysis remotely')
    parser.add_option('-o', '--output', action='store', dest='report_dir',
                      default=None,
                      help='specific the report output directory')
    parser.add_option('-T', '--testcatalog', action='store', dest='tc_host',
                      default=None,
                      help='URL to test-catalog API server')
    parser.add_option('-x', '--xmls', action='store', dest='xmls',
                      default=None,
                      help='XUnit files to parse as XML, not as plain text')
    (opts, args) = parser.parse_args()

    # cli override of config values
    if opts.configfile:
        cfg = utils.get_config(opts.configfile)
    else:
        cfg = utils.get_config()

    database = opts.database
    LOG.info("database=%s" % database)
    # database filepath might be set in config
    if database is None:
        LOG.info('get it from config')
        database = cfg.get('DEFAULT', 'database_uri')
        LOG.info('database=%s' % database)

    if opts.jenkins_host:
        jenkins_host = opts.jenkins_host
    else:
        jenkins_host = cfg.get('DEFAULT', 'jenkins_url')

    if opts.run_remote:
        run_remote = opts.run_remote
    else:
        run_remote = cfg.get('DEFAULT', 'run_remote')

    if opts.report_dir:
        reportdir = opts.report_dir
    else:
        reportdir = cfg.get('DEFAULT', 'analysis_report_dir')

    if opts.tc_host:
        tc_host = opts.tc_host
    else:
        tc_host = cfg.get('DEFAULT', 'oil_api_url')

    if opts.tc_host:
        xmls = opts.xmls
    else:
        xmls = cfg.get('DEFAULT', 'xmls_to_defer')

    if jenkins_host in [None, 'None', 'none', '']:
        LOG.error("Missing jenkins configuration")
        raise Exception("Missing jenkins configuration")

    if tc_host in [None, 'None', 'none', '']:
        LOG.error("Missing test-catalog configuration")
        raise Exception("Missing test-catalog configuration")

    # Get arguments:
    pipeline_ids = args
    if not pipeline_ids:
        raise Exception("No pipeline IDs provided")

    # Establish a connection to jenkins:
    jenkins = get_jenkins(jenkins_host, run_remote)

    # Connect to bugs DB:
    bugs = open_bug_database(database, run_remote)

    deploy_yaml_dict = {}
    prepare_yaml_dict = {}
    tempest_yaml_dict = {}
    for pipeline in pipeline_ids:
        # Make sure pipeline is in fact a pipeline id:
        if [8, 4, 4, 4, 12] != [len(x) for x in pipeline.split('-')]:
            raise Exception("Pipeline ID %s is an unrecognised format")
        deploy_build, prepare_build, tempest_build = \
            get_pipelines(pipeline, api=tc_host, remote=run_remote)
        get_triage_data(jenkins, deploy_build, 'pipeline_deploy', reportdir)
        if prepare_build:
            get_triage_data(jenkins, prepare_build,
                            'pipeline_prepare', reportdir)
        if tempest_build:
            get_triage_data(jenkins, tempest_build,
                            'test_tempest_smoke', reportdir)

        oil_df, deploy_yaml_dict = \
            process_deploy_data(pipeline, deploy_build, jenkins, reportdir,
                                bugs, deploy_yaml_dict, xmls)
        if prepare_build:
            prepare_yaml_dict = \
                process_prepare_data(pipeline, prepare_build, jenkins,
                                     reportdir, bugs, oil_df,
                                     prepare_yaml_dict, xmls)
        if tempest_build:
            tempest_yaml_dict = \
                process_tempest_data(pipeline, tempest_build, jenkins,
                                     reportdir, bugs, oil_df,
                                     tempest_yaml_dict, xmls)

    # Export to yaml:
    export_to_yaml(deploy_yaml_dict, 'pipeline_deploy', reportdir)
    export_to_yaml(prepare_yaml_dict, 'pipeline_prepare', reportdir)
    export_to_yaml(tempest_yaml_dict, 'test_tempest_smoke', reportdir)

    # Clean up data folders (just leaving yaml files):
    shutil.rmtree(os.path.join(reportdir, 'pipeline_deploy'))
    shutil.rmtree(os.path.join(reportdir, 'pipeline_prepare'))
    shutil.rmtree(os.path.join(reportdir, 'test_tempest_smoke'))


if __name__ == "__main__":
    sys.exit(main())
