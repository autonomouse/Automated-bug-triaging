#! /usr/bin/env python2

import sys
import os
import pytz
import optparse
import socket
import urlparse
import bisect
import time
import shutil
import yaml
import parsedatetime as pdt
from dateutil.parser import parse
from jenkinsapi.jenkins import Jenkins
from doberman.common import pycookiecheat, utils
from datetime import datetime
from lxml import etree

LOG = utils.get_logger('doberman.oil_stats')
_config = utils.get_config()

JENKINS_URL = _config.get('DEFAULT', 'jenkins_url')
ENVIRONMENT = _config.get('DEFAULT', 'environment')
NETLOC = _config.get('DEFAULT', 'netloc')


def date_parse(string):
    """Use two different strtotime functions to return a datetime
    object when possible.
    """

    string_spc = string.replace('_', ' ')

    try:
        return pytz.utc.localize(parse(string_spc))
    except:
        pass

    try:
        val = pdt.Calendar(pdt.Constants(usePyICU=False)).parse(string_spc)
        if val[1] > 0:  # only do strict matching
            return pytz.utc.localize(datetime(*val[0][:6]))
    except:
        pass

    raise ValueError(
        'Date format %s not understood, try 2014-02-12' % string
    )


def find_build_newer_than(builds, start):
    # assuming builds has been sorted

    # pre calculate key list
    keys = [r.get('timestamp') for r in builds]

    # make a micro timestamp from input
    start_ts = int(time.mktime(start.timetuple())) * 1000

    # find leftmost item greater than or equal to start
    i = bisect.bisect_left(keys, start_ts)
    if i != len(keys):
        return i
    return None


# jenkins job helpers
def is_running(b):
    return b['duration'] == 0


def is_good(b):
    return (not is_running(b) and b['result'] == 'SUCCESS')


def time_format(t):
    """
    Use strftime to convert to spaceless string

    param t: datetime.datetime object
    """
    return t.strftime('%Y%m%d-%H%M%S.%f')


def triage_report(triage, start, end, jenkins):
    """
    Collect data on failed builds
    for each job in the triage dictionary
        look at each job and extract:
            - console text
            - all artifacts
    write out report to oil-triage-START-END/<job>/<buildno>/<artifacts>

    param triage: dictionary with job names as keys, value
                  is a list of jenkins build objects
    """

    print('Collecting debugging data...')
    reportdir = "oil-triage-%s-%s" % (time_format(start), time_format(end))
    for job in triage.keys():
        jenkins_job = jenkins[job]
        for b in triage[job]:
            build = jenkins_job.get_build(b['number'])
            outdir = os.path.join(reportdir, job, str(b['number']))
            try:
                os.makedirs(outdir)
            except OSError:
                if not os.path.isdir(outdir):
                    raise
            with open(os.path.join(outdir, "console.txt"), "w") as c:
                print('Saving console @ %s to %s' % (build.baseurl, outdir))
                console = build.get_console()
                c.write(console)
                c.write('\n')
                c.flush()

            for a in build.get_artifacts():
                a.save_to_dir(outdir)


def print_results(results, job):
    job_dict = results['jobs'][job]

    success_rate = round(job_dict.get('success rate'), 2)

    print
    print("* {} success rate was {}%"
          .format(job, success_rate))
    print("    - Start Job: {} (Date: {})"
          .format(job_dict.get('start job'),
                  job_dict.get('start date')))
    print("    - End Job: {} (Date: {})"
          .format(job_dict.get('end job'),
                  job_dict.get('end date')))
    if job != "test_tempest_smoke":
        print("    - {} jobs, {} active, {} pass, {} fail"
              .format(job_dict.get('build objects'),
                      job_dict.get('still running'),
                      job_dict.get('passes'),
                      job_dict.get('fails')))
    else:
        print("    - {} good / {} ({} total - {} skip)"
              .format(job_dict.get('good builds'),
                      job_dict.get('total'),
                      job_dict.get('total without skipped'),
                      job_dict.get('skipped')))
    print


def print_summary(results):
    unrounded_success_rate = results['overall'].get('success rate')
    success_rate = \
        round(unrounded_success_rate, 2) if unrounded_success_rate else 0

    print
    print("Overall Success Rate: {}%".format(success_rate))
    print("    - {} tempest builds out of {} total jobs"
          .format(results['overall'].get('tempest builds'),
                  results['overall'].get('total jobs')))
    print


def main():
    parser = optparse.OptionParser()
    parser.add_option('-c', '--config', action='store', dest='configfile',
                      default=None,
                      help='specify path to configuration file')
    parser.add_option('-e', '--end', action='store', dest='end',
                      default='now',
                      help='ending date string.  Default: \'now()\'')
    parser.add_option('-E', '--environment', action='store',
                      dest='environment', default=ENVIRONMENT,
                      help='Environment in which OIL is running.' +
                           'Default: ' + ENVIRONMENT)
    parser.add_option('-H', '--host', action='store', dest='host',
                      default=JENKINS_URL,
                      help='URL to Jenkins host.' +
                           'Default: ' + JENKINS_URL)
    parser.add_option('-j', '--jobs', action='store', dest='jobs',
                      default='pipeline_deploy,pipeline_prepare' +
                              ',test_tempest_smoke',
                      help='Comma delimited list of Jenkins jobs to check.')
    parser.add_option('-k', '--keep', action='store_true', dest='keep_data',
                      default=False, help='Keep downloaded data')
    parser.add_option('-n', '--netloc', action='store', dest='netloc',
                      default=None,
                      help='Specify an IP to rewrite requests')
    parser.add_option('-o', '--outputdir', action='store', dest='download_dir',
                      default='./downloaded_data',
                      help='Folder into which to download data')
    parser.add_option('-r', '--remote', action='store_true', dest='run_remote',
                      default=False,
                      help='set if running analysis remotely')
    parser.add_option('-s', '--start', action='store', dest='start',
                      default='24 hours ago',
                      help='starting date string.  Default: \'24 hours ago\'')
    parser.add_option('-N', '--nosummary', action='store_false',
                      dest='summary', default=True,
                      help='Disable printing summary output')
    parser.add_option('-t', '--triage', action='store_true', dest='triage',
                      default=False,
                      help='Dump info on failed jobs for triage')
    (opts, args) = parser.parse_args()

    # cli override of config values
    if opts.configfile:
        cfg = utils.get_config(opts.configfile)
    else:
        cfg = utils.get_config()

    jenkins_host = None
    if opts.host:
        jenkins_host = opts.host
    else:
        jenkins_host = cfg.get('DEFAULT', 'jenkins_url')

    environment = None
    if opts.environment:
        environment = opts.environment
    else:
        environment = ENVIRONMENT

    if jenkins_host is None:
        print('Invalid Jenkins Host: %s' % (jenkins_host))
        return 1

    # cli wins, then config, then hostname lookup
    netloc_cfg = cfg.get('DEFAULT', 'netloc')
    if opts.netloc:
        netloc = opts.netloc
    elif netloc_cfg not in ['None', 'none', None]:
        netloc = netloc_cfg
    else:
        netloc = socket.gethostbyname(urlparse.urlsplit(opts.host).netloc)

    # indicate whether we're running remotely from OIL environment
    if opts.run_remote:
        run_remote = opts.run_remote
    else:
        run_remote = \
            cfg.get('DEFAULT', 'run_remote').lower() in ['true', 'yes']

    # use supplied cookie file, or fallback on users chrome cookie
    cookies = None
    if run_remote is True:
        try:
            print("Trying to find cookie in Chrome cookies")
            cookies = pycookiecheat.chrome_cookies(jenkins_host)
        except Exception:
            print("Couldn't find it")
            pass

    # convert to datetime objs
    start = date_parse(opts.start)
    if opts.end == "now":
        end = datetime.utcnow()
    else:
        end = date_parse(opts.end)

    keep_data = opts.keep_data
    download_dir = os.path.abspath(opts.download_dir)

    # Set up output dict:
    results = {'jobs': {}, 'overall': {}}

    # Inform user of environment and jenkins host:
    print('Data for OIL Environment: {} (Jenkins host: {})'
          .format(environment, opts.host))

    # connect to Jenkins
    j = Jenkins(baseurl=jenkins_host, cookies=cookies, netloc=netloc)

    totals = {}
    triage = {}

    for job in opts.jobs.split(","):
        jenkins_job = j[job]
        builds = jenkins_job._poll()['builds']
        builds.sort(key=lambda r: r.get('timestamp'))

        start_idx = find_build_newer_than(builds, start)
        end_idx = find_build_newer_than(builds, end)

        # end date is newer than we have builds, just use
        # the most recent build.
        if end_idx is None and start_idx is None:
            start_idx = builds.index(builds[-1])

        if end_idx is None:
            end_idx = builds.index(builds[-1])

        start_num = builds[start_idx]['number']
        end_num = builds[end_idx]['number']

        start_in_ms = builds[start_idx]['timestamp'] / 1000
        start_in_seconds = datetime.fromtimestamp(start_in_ms)

        end_in_ms = builds[end_idx]['timestamp'] / 1000
        end_in_seconds = datetime.fromtimestamp(end_in_ms)

        job_dict = {}
        job_dict['start job'] = start_num
        job_dict['end job'] = end_num
        job_dict['start date'] = start_in_seconds
        job_dict['end date'] = end_in_seconds

        # from idx to end
        builds_to_check = [r['number'] for r in builds[start_idx:end_idx]]
        nr_builds = len(builds_to_check)
        job_dict['build objects'] = nr_builds
        build_objs = [b for b in builds if b['number'] in builds_to_check]

        active = filter(lambda x: is_running(x) is True, build_objs)
        if job == 'test_tempest_smoke':
            tests = []
            errors = []
            failures = []
            skip = []
            for build in [bld['number'] for bld in builds[start_idx:end_idx]]:
                this_build = jenkins_job.get_build(build)
                artifacts = [b for b in this_build.get_artifacts()
                             if 'tempest_xunit.xml>' in str(b)]
                artifact = artifacts[0] if artifacts else None
                if artifact:
                    artifact_name = str(artifact).split('/')[-1].strip('>')
                    try:
                        os.makedirs(download_dir)
                    except OSError:
                        if not os.path.isdir(download_dir):
                            raise
                    xml_file = os.path.join(download_dir, artifact_name)
                    with open(artifact.save_to_dir(download_dir)):
                        parser = etree.XMLParser(huge_tree=True)
                        try:
                            doc = etree.parse(xml_file, parser).getroot()
                            tests.append(int(doc.attrib.get('tests', 0)))
                            errors.append(int(doc.attrib.get('errors', 0)))
                            failures.append(int(doc.attrib.get('failures', 0)))
                            skip.append(int(doc.attrib.get('skip', 0)))
                        except Exception, e:
                            print("'{0}' for build {1}".format(e, build))
                            print("Consider a re-run to avoid incorrect stats")
                            continue
                        artifact_rename = ("{0}_{1}.{2}".format(
                                           artifact_name.split('.')[0],
                                           str(build),
                                           artifact_name.split('.')[-1]))
                        os.rename(xml_file, xml_file.replace(artifact_name,
                                                             artifact_rename))
            n_total = (sum(tests) - sum(skip))
            n_good = n_total - (sum(errors) + sum(failures))
            success_rate = (round((float(n_good) / n_total) * 100, 2)
                            if n_total else 0)
            job_dict['good builds'] = n_good
            job_dict['total'] = n_total
            job_dict['total without skipped'] = sum(tests)
            job_dict['skipped'] = sum(skip)
            job_dict['success rate'] = success_rate

            nr_nab = nr_builds - len(active)
        else:
            # TODO: handle case where we don't have active, good or bad builds
            good = filter(lambda x: is_good(x), build_objs)
            bad = filter(lambda x: is_good(x) is False and
                         is_running(x) is False, build_objs)
            nr_nab = nr_builds - len(active)
            success_rate = (float(len(good)) / float(nr_nab) * 100.0
                            if nr_nab else 0)
            # pipeline_deploy 11 active, 16/31 = 58.68% passing
            # Total: 31 builds, 12 active, 2 failed, 17 pass.
            # Success rate: 17 / (31 - 12) = 89%

            job_dict['still running'] = len(active)
            job_dict['passes'] = len(good)
            job_dict['fails'] = len(bad)
            job_dict['completed builds'] = nr_nab
            job_dict['success rate'] = success_rate

        results['jobs'][job] = job_dict

        totals[job] = {'total_builds': nr_nab, 'passing': len(good)}
        triage[job] = bad

    # report results:
    for job in opts.jobs.split(","):
        # I wanted to do "for job in results.keys():" here, but then they
        # wouldn't be reported in the correct order.
        print_results(results, job)

    # overall success
    if opts.summary:
        tt = totals['test_tempest_smoke']['total_builds']
        td = totals['pipeline_deploy']['total_builds']
        overall = (float(tt) / float(td) * 100.0) if td else 0

        results['overall']['success rate'] = overall
        results['overall']['tempest builds'] = tt
        results['overall']['total jobs'] = td

        print_summary(results)

    # save results to file:
    with open("results.yaml", "w") as output:
        # TODO: better output location than cwd needed!
        output.write(yaml.safe_dump(results))

    # triage report
    if opts.triage:
        print('Running triage_report')
        triage_report(triage, start, end, j)

    if os.path.isdir(download_dir) and not keep_data:
        shutil.rmtree(download_dir)


if __name__ == '__main__':
    sys.exit(main())
