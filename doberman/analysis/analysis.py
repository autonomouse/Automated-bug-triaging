#! /usr/bin/env python2

import sys
import subprocess
import os
import re
import yaml
import pandas as pd
import json
import socket
import urlparse
import tarfile
import shutil
import uuid
from pandas import DataFrame, Series
from lxml import etree
from jenkinsapi.jenkins import Jenkins
from doberman.common import pycookiecheat, utils

LOG = utils.get_logger('doberman.analysis')


def connect_to_jenkins(url="http://oil-jenkins.canonical.com",
                       jenkins_auth="oil-jenkins-auth.json"):
    """ Connects to jenkins via jenkinsapi, returns a jenkins object. """
    netloc = socket.gethostbyname(urlparse.urlsplit(url).netloc)
    cookies = pycookiecheat.chrome_cookies(url)
    return Jenkins(baseurl=url, cookies=cookies, netloc=netloc)


def get_pipelines(pipeline, remote=False):
    """ Using test-catalog, return the build numbers for the jobs
        that are part of the given pipeline.

    """
    api = "https://oil.canonical.com/api/"
    if remote:
        auth_file = "oil-auth.json"
        cookies = pycookiecheat.chrome_cookies(api)
        with open(auth_file, "w") as o:
            o.write(json.dumps(cookies))
            o.close()
        p1 = subprocess.Popen(['test-catalog', '-e', api, '-t',
                              auth_file, '-p', pipeline],
                              stdout=subprocess.PIPE)
    else:
        p1 = subprocess.Popen(['test-catalog', '-p', pipeline],
                              stdout=subprocess.PIPE)
    output = p1.communicate()[0]
    if output == '':
        raise("Test catalog(ue) error")
    try:
        deploy_build = \
            output.split("jenkins-pipeline_deploy-")[1].split(' ')[0]
    except:
        deploy_build = None
    try:
        prepare_build = \
            output.split("jenkins-pipeline_prepare-")[1].split(' ')[0]
    except:
        prepare_build = None
    try:
        tempest_build = \
            output.split("jenkins-test_tempest_smoke-")[1].split(' ')[0]
    except:
        tempest_build = None
    return (deploy_build, prepare_build, tempest_build)


def get_triage_data(jenkins, build_num, job, reportdir):
    """ get the artifacts from jenkins via jenkinsapi object. """
    jenkins_job = jenkins[job]
    build = jenkins_job.get_build(int(build_num))
    outdir = os.path.join(reportdir, job, str(build_num))
    print 'Downloading debug data to: %s' % (outdir)
    try:
        os.makedirs(outdir)
    except OSError:
        if not os.path.isdir(outdir):
            raise
    with open(os.path.join(outdir, "console.txt"), "w") as c:
        print 'Saving console @ %s to %s' % (build.baseurl, outdir)
        console = build.get_console()
        c.write(console)
        c.write('\n')
        c.flush()

    for artifact in build.get_artifacts():
        artifact.save_to_dir(outdir)
        extract_and_delete_archive(outdir, artifact)


def extract_and_delete_archive(outdir, artifact):
    """
    Extracts the contents of a tarball and places it into a new file of the
    samename without the .tar.gz suffix (N.B. this leaves .ring.gz intact
    as they seem to contain binary ring files that I'm not sure what to do with
    at this point).
    """

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


def process_deploy_data(pipeline, deploy_build, jenkins, reportdir,
                        bugs, yaml_dict):
    """ Parses the artifacts files from a single pipeline into data and
    metadata DataFrames """
    pipeline_deploy_path = os.path.join(reportdir, 'pipeline_deploy',
                                        deploy_build)

    # Get paths of data files:
    oil_node_location = os.path.join(pipeline_deploy_path, 'oil_nodes')
    juju_status_location = os.path.join(pipeline_deploy_path,
                                        'juju_status.yaml')
    pipeline_status_location = os.path.join(pipeline_deploy_path,
                                            'pipeline_status')
    mapping_location = os.path.join(pipeline_deploy_path, 'mapping.json')
    console_location = os.path.join(pipeline_deploy_path, 'console.txt')

    # Get console output:
    with open(console_location, 'r') as grep_me:
        console_output = grep_me.read()

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
                serv_key = key.replace('/', '').replace('0', '')
                unit[serv_key] = \
                    juju_status['services'][serv]['units'][key]
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
        bug_hunt('pipeline_deploy', jenkins, deploy_build, bugs, reportdir,
                 oil_df, 'console.txt', console_output)
    yaml_dict = add_to_yaml(pipeline, deploy_build, bugs, matching_bugs,
                            build_status, existing_dict=yaml_dict)
    return (oil_df, yaml_dict)


def process_prepare_data(pipeline, prepare_build, jenkins, reportdir,
                         bugs, oil_df, yaml_dict):
    """ Parses the artifacts files from a single pipeline into data and
    metadata DataFrames """
    prepare_path = os.path.join(reportdir, 'pipeline_prepare',
                                prepare_build)

    # Get paths of data files:
    console_location = os.path.join(prepare_path, 'console.txt')

    # Get console output:
    with open(console_location, 'r') as grep_me:
        console_output = grep_me.read()

    matching_bugs, build_status = \
        bug_hunt('pipeline_prepare', jenkins, prepare_build, bugs, reportdir,
                 oil_df, 'console.txt', console_output)

    yaml_dict = add_to_yaml(pipeline, prepare_build, bugs, matching_bugs,
                            build_status, existing_dict=yaml_dict)
    return yaml_dict


def process_tempest_data(pipeline, tempest_build, jenkins, reportdir,
                         bugs, oil_df, yaml_dict):
    """ Parses the artifacts files from a single pipeline into data and
    metadata DataFrames """
    tts_path = os.path.join(reportdir, 'test_tempest_smoke', tempest_build)

    # Get paths of data files:
    console_location = os.path.join(tts_path, 'console.txt')
    tempest_xml_location = os.path.join(tts_path, 'tempest_xunit.xml')

    # Get console output:
    with open(console_location, 'r') as grep_me:
        console_output = grep_me.read()

    # Check console
    matching_bugs, build_status = \
        bug_hunt('test_tempest_smoke', jenkins, tempest_build, bugs, reportdir,
                 oil_df, 'console.txt', console_output)

    # Get tempest results:
    doc = etree.parse(tempest_xml_location).getroot()
    errors_and_fails = doc.xpath('.//failure') + doc.xpath('.//error')
    for num, fail in enumerate(errors_and_fails):
        pre_log = fail.get('message').split("begin captured logging")[0]
        earlier_matching_bugs = matching_bugs
        matching_bugs, build_status = \
            bug_hunt('test_tempest_smoke', jenkins, tempest_build, bugs,
                     reportdir, oil_df, 'tempest_xunit.xml', pre_log)

        # Merge matching_bugs dictionaries:
        matching_bugs = dict(list(earlier_matching_bugs.items()) +
                             list(matching_bugs.items()))

    yaml_dict = add_to_yaml(pipeline, tempest_build, bugs, matching_bugs,
                            build_status, existing_dict=yaml_dict)
    return yaml_dict


def bug_hunt(job, jenkins, build, bugs, reportdir, oil_df,
             target, text_to_grep):
    """ Searches provided text for each regexp from the bugs database. """
    build_status = \
        [build_info for build_info in jenkins[job]._poll()['builds']
         if build_info['number'] == int(build)][0]['result']
    matching_bugs = {}
    units_list = oil_df['service'].tolist()
    machines_list = oil_df['node'].tolist()
    vendors_list = oil_df['vendor'].tolist()
    bug_unmatched = True
    for bug_id in bugs.keys():
        if job in bugs[bug_id]:
            # TODO: This will probably need to be changed once we're using a DB
            regexp = bugs[bug_id][job]['regexp']
            if regexp not in ['None', None, '']:
                if target == bugs[bug_id][job]['target_file']:
                    #bug_category = bugs[bug_id][job]['target_file']
                    matches = \
                        re.compile(regexp, re.DOTALL).findall(text_to_grep)
                    if len(matches):
                        # TODO: For now, we'll just include everything
                        # - guilt by association - but the next step would be
                        # to only associate the machines implied by
                        # bug_category
                        matching_bugs[bug_id] = {'regexp': regexp,
                                                 'vendors': vendors_list,
                                                 'machines': machines_list,
                                                 'units': units_list}
                        bug_unmatched = False
    if bug_unmatched:
        # Placeholder until I work out what to put here. Include traceback.
        matching_bugs['unfiled-' + str(uuid.uuid4())] = \
            {'regexp': 'UNMATCHED BUG',
             'vendors': vendors_list,
             'machines': machines_list,
             'units': units_list}
    return (matching_bugs, build_status)


def add_to_yaml(pline, build, bugs, matching_bugs, build_status,
                existing_dict=None):
    """ Creates a yaml dict and populates with data in the right
        format and merges with existing yaml dict.

    """
    # Make dict
    yaml_dict = {}
    if matching_bugs != {}:
        yaml_dict['pipeline'] = {pline: {'status': build_status,
                                         'build': build,
                                         'bugs': matching_bugs}}
    # Merge with existing dict:
    if existing_dict:
        yaml_dict = \
            dict(list(existing_dict.items()) + list(yaml_dict.items()))

    return yaml_dict


def export_to_yaml(yaml_dict, job, reportdir):
    """ . """
    filename = 'triage_' + job + '.yml'
    OPfile_path = os.path.join(reportdir, filename)
    with open(OPfile_path, 'w') as outfile:
        outfile.write(yaml.safe_dump(yaml_dict, default_flow_style=False))
        print(filename + " written to " + reportdir)


def main():
    cfg = utils.get_config()

    jenkins = connect_to_jenkins()
    # try:
    #     pipeline_ids = sys.argv[1:]
    # except:
    # 	pass
    # pipeline_ids = \
    #    ["c1aa5aae-08f0-4f4f-809e-4f28fa052dbc"] \
    #         if pipeline_ids == None else pipeline_ids

    # Mock data (will be a list eventually)
    pipeline_ids = ["4c657c2d-ef25-44fb-b17a-ccdf290d89f7",
                    "1b07c919-776c-4092-b010-15085ec8caea",
                    "4456de2f-0043-49f2-870f-10a2e35e9de8"]

    reportdir = cfg.get('DEFAULT', 'analysis_report_dir')

    # Temporarily use mock_database yaml file, not db:
    mock_database_file = cfg.get('DEFAULT', 'database_uri')

    with open(mock_database_file, "r") as mock_db_file:
        mock_db = yaml.load(mock_db_file)
    bugs = mock_db['bugs']

    # Clean up data folders:
    if os.path.isdir(reportdir):
        shutil.rmtree(reportdir)

    deploy_yaml_dict = {}
    prepare_yaml_dict = {}
    tempest_yaml_dict = {}
    for pipeline in pipeline_ids:
        deploy_build, prepare_build, tempest_build = \
            get_pipelines(pipeline, remote=True)
        get_triage_data(jenkins, deploy_build, 'pipeline_deploy', reportdir)
        if prepare_build:
            get_triage_data(jenkins, prepare_build,
                            'pipeline_prepare', reportdir)
        if tempest_build:
            get_triage_data(jenkins, tempest_build,
                            'test_tempest_smoke', reportdir)

        oil_df, deploy_yaml_dict = \
            process_deploy_data(pipeline, deploy_build, jenkins, reportdir,
                                bugs, deploy_yaml_dict)
        if prepare_build:
            prepare_yaml_dict = \
                process_prepare_data(pipeline, prepare_build, jenkins,
                                     reportdir, bugs, oil_df,
                                     prepare_yaml_dict)
        if tempest_build:
            tempest_yaml_dict = \
                process_tempest_data(pipeline, tempest_build, jenkins,
                                     reportdir, bugs, oil_df,
                                     tempest_yaml_dict)

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
