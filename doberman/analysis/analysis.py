#! /usr/bin/env python2

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
from jenkinsapi.jenkins import Jenkins
from jenkinsapi.custom_exceptions import *
from doberman.common import pycookiecheat, utils

tc_client = TCClient
LOG = utils.get_logger('doberman.analysis')
_tc_client = []
_jenkins = []

# Special cases: A hard-coded dictionary linking the files that may be missing
# to a bug id on launchpad:
# TODO: Decide whether to keep this hard-coded or to use an external yaml, etc:
special_cases = {'juju_status.yaml': '1372407',
                 'oil_nodes': '1372411',
                 'pipeline_id': '1372567'}


def get_jenkins(url, netloc, remote=False):
    if _jenkins and not url:
        return _jenkins[0]

    jenkins = connect_to_jenkins(url, netloc, remote)
    _jenkins.append(jenkins)
    return jenkins


def get_tc_client(api, cookie=None, remote=False):
    if _tc_client and not api:
        return _tc_client[0]

    tc_client = connect_to_testcatalog(api, cookie=cookie, remote=remote)
    _tc_client.append(tc_client)
    return tc_client


def connect_to_testcatalog(api, cookie=None, remote=False):
    LOG.debug('Connecting to test-catalog @ %s remote=%s' % (api, remote))
    if cookie is None:
        LOG.info("Fetching test-catalog cookies for %s" % api)
        cookie = pycookiecheat.chrome_cookies(api)
    LOG.info("Fetching test-catalog using endpoint=%s" % (api))
    return tc_client(endpoint=api, cookies=cookie)


def connect_to_jenkins(url, netloc, remote=False):
    """ Connects to jenkins via jenkinsapi, returns a jenkins object. """

    LOG.debug('Connecting to jenkins @ %s remote=%s' % (url, remote))
    cookies = None

    if remote:
        LOG.info("Fetching cookies for %s" % url)
        cookies = pycookiecheat.chrome_cookies(url)
    try:
        return Jenkins(baseurl=url, cookies=cookies, netloc=netloc)
    except JenkinsAPIException:
        LOG.exception('Failed to connect to Jenkins')


def get_pipelines(pipeline, api, tc_auth, remote=False):
    """ Using test-catalog, return the build numbers for the jobs that are
        part of the given pipeline.

    """
    LOG.info('Fetching data on pipeline: %s' % (pipeline))
    client = get_tc_client(api, cookie=tc_auth, remote=remote)
    try:
        pl_tcat = TCCTestPipeline(client, pipeline)
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


def get_triage_data(jenkins, build_num, job, reportdir):
    """ Get the artifacts from jenkins via jenkinsapi object. """
    jenkins_job = jenkins[job]
    build = jenkins_job.get_build(int(build_num))
    outdir = os.path.join(reportdir, job, str(build_num))
    LOG.info('Downloading debug data to: %s' % (outdir))
    # Check to make sure it is not still running!:
    if build._data['duration'] == 0:
        return True
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
    return False


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


def get_yaml(file_location, pline, build, yaml_dict, jurl):
    try:
        with open(file_location, "r") as f:
            return (yaml.load(f), yaml_dict)
    except IOError, e:
        file_name = file_location.split('/')[-1]
        LOG.error("%s: %s is not in artifacts folder (%s)"
                  % (pline, file_name, e[1]))
        msg = file_name + ' MISSING'
        yaml_dict = non_db_bug(pline, build, special_cases[file_name],
                               yaml_dict, 'FAILURE', msg, jurl)
        return (None, yaml_dict)


def non_db_bug(pline, build, bug_id, existing_dict, status, err_msg, jurl):
    """ Make non-database bugs for special cases, such as missing files that
        cannot be, or are not yet, listed in the bugs database.

    """
    matching_bugs = {}
    matching_bugs[bug_id] = {'regexps': err_msg, 'vendors': err_msg,
                             'machines': err_msg, 'units': err_msg}
    yaml_dict = add_to_yaml(pline, build, matching_bugs, 'FAILURE', None,
                            existing_dict=existing_dict)
    return yaml_dict


def process_deploy_data(pline, deploy_build, jenkins, reportdir, bugs, jurl,
                        yaml_dict, xmls):
    """ Parses the artifacts files from a single pipeline into data and
        metadata DataFrames

    """
    pipeline_deploy_path = os.path.join(reportdir, 'pipeline_deploy',
                                        deploy_build)

    oil_df = DataFrame(columns=('node', 'vendor', 'service'))

    # Read oil nodes file:
    oil_node_location = os.path.join(pipeline_deploy_path, 'oil_nodes')
    oil_nodes_yml, yaml_dict = get_yaml(oil_node_location, pline,
                                        deploy_build, yaml_dict, jurl)
    if not oil_nodes_yml:
        return (oil_df, yaml_dict)
    else:
        oil_nodes = DataFrame(oil_nodes_yml['oil_nodes'])
        oil_nodes.rename(columns={'host': 'node'}, inplace=True)

    # Read juju status file:
    juju_status_location = os.path.join(pipeline_deploy_path,
                                        'juju_status.yaml')
    juju_status, yaml_dict = get_yaml(juju_status_location, pline,
                                      deploy_build, yaml_dict, jurl)
    if not juju_status:
        return (oil_df, yaml_dict)

    row = 0
    for service in juju_status['services']:
        if 'units' in juju_status['services'][service]:
            units = juju_status['services'][service]['units']
        else:
            units = {}
            oil_df.loc[row] = ['N/A', 'N/A', 'N/A']
        for unit in units:
            this_unit = units[unit]
            machine = this_unit['public-address'] if 'public-address'\
                in this_unit else "N/A"
            nptags = oil_nodes[oil_nodes['node'] == machine]['tags']\
                .apply(str)
            tags_list = nptags.tolist()
            if tags_list:
                tags = tags_list[0].replace("[", "").replace("]", "")\
                    .split(', ')
                hardware = [tag.replace("'", "") for tag in tags if 'hardware'
                            in tag]
            else:
                hardware = ['N/A']
            oil_df.loc[row] = [machine, unit, ', '.join(hardware)
                               .replace('hardware-', '')]
            row += 1

    matching_bugs, build_status, link2 = bug_hunt('pipeline_deploy', jenkins,
                                                  deploy_build, bugs, oil_df,
                                                  pipeline_deploy_path, xmls)
    yaml_dict = add_to_yaml(pline, deploy_build, matching_bugs, build_status,
                            jurl + link2, existing_dict=yaml_dict)
    return (oil_df, yaml_dict)


def process_prepare_data(pline, prepare_build, jenkins, reportdir, bugs, jurl,
                         oil_df, yaml_dict, xmls):
    """ Parses the artifacts files from a single pipeline into data and
        metadata DataFrames.

    """
    prepare_path = os.path.join(reportdir, 'pipeline_prepare',
                                prepare_build)
    matching_bugs, build_status, link2 = \
        bug_hunt('pipeline_prepare', jenkins, prepare_build, bugs, oil_df,
                 prepare_path, xmls)

    yaml_dict = add_to_yaml(pline, prepare_build, matching_bugs, build_status,
                            jurl + link2, existing_dict=yaml_dict)
    return yaml_dict


def process_tempest_data(pline, tempest_build, jenkins, reportdir, bugs, jurl,
                         oil_df, yaml_dict, xmls):
    """
    Parses the artifacts files from a single pipeline into data and
    metadata DataFrames

    """
    tts_path = os.path.join(reportdir, 'test_tempest_smoke', tempest_build)

    matching_bugs, build_status, link2 = \
        bug_hunt('test_tempest_smoke', jenkins, tempest_build, bugs, oil_df,
                 tts_path, xmls)
    yaml_dict = add_to_yaml(pline, tempest_build, matching_bugs, build_status,
                            jurl + link2, existing_dict=yaml_dict)
    return yaml_dict


def bug_hunt(job, jenkins, build, bugs, oil_df, path, parse_as_xml=[]):
    """ Using information from the bugs database, opens target file and
        searches the text for each associated regexp. """
    # TODO: As it stands, files are only searched if there is an entry in the
    # DB. This shouldn't be a problem if there is always a dummy bug in the DB
    # for the important files such as console and tempest_xunit.xml FOR EACH
    # JOB TYPE (i.e. pipeline_deploy, pipeline_prepare and test_tempest_smoke).
    build_status = [build_info for build_info in jenkins[job]._poll()['builds']
                    if build_info['number'] == int(build)][0]['result']
    matching_bugs = {}
    units_list = oil_df['service'].tolist()
    machines_list = oil_df['node'].tolist()
    vendors_list = oil_df['vendor'].tolist()
    bug_unmatched = True
    info = {}
    if not bugs:
        raise Exception("No bugs in database!")
    for bug_id in bugs.keys():
        if job in bugs[bug_id]:
            # Any of the dicts in bugs[bug_id][job] can match (or):
            or_dict = bugs[bug_id][job]
            for and_dict in or_dict:
                # Within the dictionary all have to match (and):
                hit_dict = {}
                # Load up the file for each target_file in the DB for this bug:
                for target_file in and_dict.keys():
                    target_location = os.path.join(path, target_file)
                    if not os.path.isfile(target_location):
                        info['error'] = target_file + " not present"
                        break
                    if target_file == 'console.txt':
                        link2 = '/job/%s/%s/console' % (job, build)
                    else:
                        link2 = ('/job/%s/%s/artifact/artifacts/%s'
                                 % (job, build, target_file))
                    if not (target_file in parse_as_xml):
                        with open(target_location, 'r') as grep_me:
                            text = grep_me.read()
                        hit = rematch(and_dict, target_file, text)
                        if hit:
                            hit_dict = join_dicts(hit_dict, hit)
                        else:
                            info['target file'] = target_file
                            info['text'] = text
                    else:
                        # Get tempest results:
                        p = etree.XMLParser(huge_tree=True)
                        doc = etree.parse(target_location, parser=p).getroot()
                        errors_and_fails = doc.xpath('.//failure')
                        errors_and_fails += doc.xpath('.//error')
                        # TODO: There is not currently a way to do multiple
                        # 'and' regexps within a single tempest file - you can
                        # do console AND tempest or tempest OR tempest, but not
                        # tempest AND tempest. Needs it please!
                        for num, fail in enumerate(errors_and_fails):
                            pre_log = fail.get('message')\
                                .split("begin captured logging")[0]
                            hit = rematch(and_dict, target_file, pre_log)
                            if hit:
                                hit_dict = join_dicts(hit_dict, hit)
                            else:
                                info['target file'] = target_file
                                info['text'] = pre_log
                            info['xunit class'] = \
                                fail.getparent().get('classname')
                            info['xunit name'] = fail.getparent().get('name')

                if and_dict == hit_dict:
                    matching_bugs[bug_id] = {'regexps': hit_dict,
                                             'vendors': vendors_list,
                                             'machines': machines_list,
                                             'units': units_list}
                    if info:
                        matching_bugs[bug_id]['additional info'] = info
                    LOG.info("Bug found!")
                    LOG.info(hit_dict)
                    hit_dict = {}
                    bug_unmatched = False
                    break
    if bug_unmatched and build_status == 'FAILURE':
        bug_id = 'unfiled-' + str(uuid.uuid4())
        matching_bugs[bug_id] = {'regexps': 'NO REGEX - UNFILED/UNMATCHED BUG',
                                 'vendors': vendors_list,
                                 'machines': machines_list,
                                 'units': units_list}
        LOG.info("Unfiled bug found!")
        hit_dict = {}
        if info:
            matching_bugs[bug_id]['additional info'] = info
    return (matching_bugs, build_status, link2)


def rematch(bugs, target_file, text):
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
        if matches:
            if len(set_re) == len(set(matches)):
                return {target_file: {'regexp': regexps}}


def add_to_yaml(pline, build, matching_bugs, build_status, link,
                existing_dict=None):
    """
    Creates a yaml dict and populates with data in the right format and merges
    with existing yaml dict.

    """
    # Make dict
    pipeline_dict = {}
    yaml_dict = {}

    if matching_bugs != {}:
        pipeline_dict = {pline: {'status': build_status,
                                 'build': build,
                                 'bugs': matching_bugs}}
        if link:
            pipeline_dict[pline]['link to jenkins'] = link

    # Merge with existing dict:
    if existing_dict:
        if 'pipeline' in existing_dict:
            yaml_dict['pipeline'] = join_dicts(existing_dict['pipeline'],
                                               pipeline_dict)
        else:
            yaml_dict['pipeline'] = join_dicts(existing_dict, pipeline_dict)
    else:
        yaml_dict['pipeline'] = pipeline_dict
    return yaml_dict


def export_to_yaml(yaml_dict, job, reportdir):
    """ Write output files. """
    filename = 'triage_' + job + '.yml'
    file_path = os.path.join(reportdir, filename)
    if not os.path.isdir(reportdir):
        os.makedirs(reportdir)
    with open(file_path, 'w') as outfile:
        outfile.write(yaml.safe_dump(yaml_dict, default_flow_style=False))
        LOG.info(filename + " written to " + reportdir)


def open_bug_database(database_uri, api, tc_auth, remote=False):
    if database_uri in [None, 'None', 'none', '']:
        LOG.info("Connecting to test-catalog bug/regex database")
        client = get_tc_client(api, cookie=tc_auth, remote=remote)
        return client.get_bug_info(force_refresh=True)
    elif len(database_uri):
        if not database_uri.startswith("/"):
            filename = os.path.join(os.getcwd(), database_uri)

        LOG.info("Connecting to database file: %s" % (filename))
        with open(filename, "r") as mock_db_file:
            return yaml.load(mock_db_file)['bugs']
    else:
        LOG.error('Unknown database: %s' % (database_uri))
        raise Exception('Invalid Database configuration')


def join_dicts(old_dict, new_dict):
    """ Merge matching_bugs dictionaries. """
    earlier_items = list(old_dict.items())
    current_items = list(new_dict.items())
    return dict(earlier_items + current_items)


def remove_dirs(rootdir, folders_to_delete):
    for folder in folders_to_delete:
        kill_me = os.path.join(rootdir, folder)
        if os.path.isdir(kill_me):
            shutil.rmtree(kill_me)


def get_pipeline_from_deploy_build_number(jenkins, id_number):
    deploy_bld_n = int(id_number)
    try:
        cons = jenkins['pipeline_deploy'].get_build(deploy_bld_n).get_console()
    except:
        msg = "Failed to fetch pipeline from deploy build: \"%s" % idn
        msg += "\" - if this is already a pipeline id, run without the"
        msg += " '-b' flag."
        raise Exception(msg)
    pl = cons.split('pipeline_id')[1].split('|\n')[0].replace('|', '').strip()
    if pipeline_check(pl):
        return pl
    else:
        pl = cons.split('PIPELINE_ID=')[1].replace('\n++ ', '')
        if pipeline_check(pl):
            return pl
        else:
            msg = "Pipeline ID \"%s\" is an unrecognised format" % pl
            LOG.error(msg)
            raise Exception(msg)


def pipeline_check(pipeline_id):
    return [8, 4, 4, 4, 12] == [len(x) for x in pipeline_id.split('-')]


def main():
    usage = "usage: %prog [options] pipeline_id1 pipeline_id2 ..."
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-b', '--usebuildnos', action='store_true',
                      dest='use_deploy', default=False,
                      help='use pipeline_deploy build numbers, not pipelines')
    parser.add_option('-c', '--config', action='store', dest='configfile',
                      default=None,
                      help='specify path to configuration file')
    parser.add_option('-d', '--dburi', action='store', dest='database',
                      default=None,
                      help='set URI to bug/regex db: /path/to/mock_db.yaml')
    parser.add_option('-J', '--jenkins', action='store', dest='jenkins_host',
                      default=None,
                      help='URL to Jenkins server')
    parser.add_option('-k', '--keep', action='store_true', dest='keep_data',
                      default=False,
                      help='Do not delete extracted tarballs when finished')
    parser.add_option('-n', '--netloc', action='store', dest='netloc',
                      default=None,
                      help='Specify an IP to rewrite URLs')
    parser.add_option('-o', '--output', action='store', dest='report_dir',
                      default=None,
                      help='specific the report output directory')
    parser.add_option('-r', '--remote', action='store_true', dest='run_remote',
                      default=False,
                      help='set if running analysis remotely')
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

    if opts.use_deploy:
        use_deploy = opts.use_deploy
    else:
        use_deploy = cfg.get('DEFAULT', 'use_deploy').lower() in \
            ['true', 'yes']

    if opts.jenkins_host:
        jenkins_host = opts.jenkins_host
    else:
        jenkins_host = cfg.get('DEFAULT', 'jenkins_url')

    # cli wins, then config, then hostname lookup
    netloc_cfg = cfg.get('DEFAULT', 'netloc')
    if opts.netloc:
        netloc = opts.netloc
    elif netloc_cfg not in ['None', 'none', None]:
        netloc = netloc_cfg
    else:
        netloc = socket.gethostbyname(urlparse.urlsplit(opts.host).netloc)

    if opts.run_remote:
        run_remote = opts.run_remote
    else:
        run_remote = \
            cfg.get('DEFAULT', 'run_remote').lower() in ['true', 'yes']

    if opts.report_dir:
        reportdir = opts.report_dir
    else:
        reportdir = cfg.get('DEFAULT', 'analysis_report_dir')

    if opts.tc_host:
        tc_host = opts.tc_host
    else:
        tc_host = cfg.get('DEFAULT', 'oil_api_url')

    if opts.keep_data:
        keep_data = opts.keep_data
    else:
        keep_data = cfg.get('DEFAULT', 'keep_data').lower() in ['true', 'yes']

    if opts.xmls:
        xmls = opts.xmls
    else:
        xmls = cfg.get('DEFAULT', 'xmls_to_defer')
    xmls = xmls.replace(' ', '').split(',')

    if jenkins_host in [None, 'None', 'none', '']:
        LOG.error("Missing jenkins configuration")
        raise Exception("Missing jenkins configuration")

    if tc_host in [None, 'None', 'none', '']:
        LOG.error("Missing test-catalog configuration")
        raise Exception("Missing test-catalog configuration")

    # Get arguments:
    ids = set(args)
    if not ids:
        raise Exception("No pipeline IDs provided")

    # Establish a connection to jenkins:
    jenkins = get_jenkins(jenkins_host, netloc, run_remote)

    # Connect to bugs DB:
    tc_auth = json.load(open(cfg.get('DEFAULT', 'tc_auth')))
    LOG.debug('tc_auth token=%s' % (tc_auth))

    bugs = open_bug_database(database, tc_host, tc_auth, run_remote)

    deploy_yaml_dict = {}
    prepare_yaml_dict = {}
    tempest_yaml_dict = {}
    pipeline_ids = []
    problem_pipelines = []

    # If using build numbers instead of pipelines, get pipeline:
    if use_deploy:
        msg = "Looking up pipeline ids for the following jenkins "
        msg += "pipeline_deploy build numbers: %s"
        LOG.info(msg % ", ".join([str(i) for i in ids]))

    if len(ids) > 35:
        report_at = range(5, 100, 5)  # Notify every 5 percent complete
    elif len(ids) > 25:
        report_at = range(10, 100, 10)  # Notify every 10 percent complete
    elif len(ids) > 10:
        report_at = range(25, 100, 25)  # Notify every 25 percent complete
    else:
        report_at = [50]  # Notify at 50 percent complete

    for pos, idn in enumerate(ids):
        if use_deploy:
            pipeline = get_pipeline_from_deploy_build_number(jenkins, idn)
        else:
            pipeline = idn
        # Quickly cycle through to check all pipelines are real:
        if not pipeline_check(pipeline):
            msg = "Pipeline ID \"%s\" is an unrecognised format" % pipeline
            LOG.error(msg)
            raise Exception(msg)
        pipeline_ids.append(pipeline)

        # Notify user/log of progress
        progress = [round((pc / 100.0) * len(ids)) for pc in report_at]
        if pos in progress:
            LOG.info("Pipeline lookup " + str(report_at[progress.index(pos)])
                     + "% complete.")
    LOG.info("All pipelines checked. Now polling jenkins and processing data.")

    for pipeline in pipeline_ids:
        try:
            # Now go through again and get pipeline data then process each:
            deploy_build, prepare_build, tempest_build = \
                get_pipelines(pipeline, tc_host, tc_auth, remote=run_remote)

            # Pull console and artifacts from jenkins:
            still_running = get_triage_data(jenkins, deploy_build,
                                            'pipeline_deploy', reportdir)
            if not still_running:
                if prepare_build:
                    get_triage_data(jenkins, prepare_build,
                                    'pipeline_prepare', reportdir)
                if tempest_build:
                    get_triage_data(jenkins, tempest_build,
                                    'test_tempest_smoke', reportdir)

                # Process downloaded data:
                oil_df, deploy_yaml_dict = \
                    process_deploy_data(pipeline, deploy_build, jenkins,
                                        reportdir, bugs, jenkins_host,
                                        deploy_yaml_dict, xmls)
                if prepare_build:
                    prepare_yaml_dict = \
                        process_prepare_data(pipeline, prepare_build, jenkins,
                                             reportdir, bugs, jenkins_host,
                                             oil_df, prepare_yaml_dict, xmls)

                if tempest_build:
                    tempest_yaml_dict = \
                        process_tempest_data(pipeline, tempest_build, jenkins,
                                             reportdir, bugs, jenkins_host,
                                             oil_df, tempest_yaml_dict, xmls)
            else:
                LOG.error("%s is still running - skipping" % deploy_build)
        except:
            if 'deploy_build' not in locals():
                deploy_build = "cannot acquire pipeline deploy build number."
                deploy_yaml_dict = non_db_bug(pipeline, deploy_build,
                                              special_cases['pipeline_id'],
                                              deploy_yaml_dict, 'FAILURE',
                                              deploy_build, jenkins_host)
            else:
                print("Problem with " + pipeline + " - skipping (deploy_build:"
                      + " " + deploy_build + ")")
                problem_pipelines.append((pipeline, deploy_build))

    # Export to yaml:
    export_to_yaml(deploy_yaml_dict, 'pipeline_deploy', reportdir)
    export_to_yaml(prepare_yaml_dict, 'pipeline_prepare', reportdir)
    export_to_yaml(tempest_yaml_dict, 'test_tempest_smoke', reportdir)

    # Write to file any pipelines (plus deploy build) that failed processing:
    if not problem_pipelines == []:
        file_path = os.path.join(reportdir, 'problem_pipelines.yaml')
        open(file_path, 'a').close()  # Create file if doesn't exist yet
        with open(file_path, 'r+') as pp_file:
            existing_content = pp_file.read()
            pp_file.seek(0, 0)  # Put at beginning of file
            pp_file.write("\n" + str(datetime.datetime.now())
                          + "\n--------------------------\n")
            for problem_pipeline in problem_pipelines:
                pp_file.write("%s (deploy build: %s) \n" % problem_pipeline)
            pp_file.write(existing_content)
            errmsg = "There were some pipelines that could not be processed. "
            errmsg += "This information was written to problem_pipelines.yaml "
            errmsg += "in " + reportdir + "\n\n"
            LOG.error(errmsg)

    # Clean up data folders (just leaving yaml files):
    if not keep_data:
        remove_dirs(reportdir, ['pipeline_deploy', 'pipeline_prepare',
                                'test_tempest_smoke'])


if __name__ == "__main__":
    sys.exit(main())
