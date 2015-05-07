#!/usr/bin/python

import argparse
import json
import yaml
from test_catalog.client.api import TCClient as tc_client
from pprint import pprint


DEFAULT_DB = 'samples/mock_database.yml'
DEFAULT_TOKEN = 'test-catalog-auth.json'
DEFAULT_ENDPOINT = 'https://oil.canonical.com/api/'


def parse():
    parser = argparse.ArgumentParser(
        description='Upload bugs to remote database.'
    )
    parser.add_argument('-d', '--database', default=DEFAULT_DB,
                        help='Location of yaml to upload to the database.')
    parser.add_argument('-e', '--endpoint', default=DEFAULT_ENDPOINT,
                        help='Remote test-catalog URL for database interface.')
    parser.add_argument('-f', '--force', default=False, action='store_true',
                        help='Delete ophan bugs without asking.')
    parser.add_argument('-r', '--dryrun', default=False, action='store_true',
                        help='Does not make any changes to the database.')
    parser.add_argument('-t', '--token', default=DEFAULT_TOKEN,
                        help='Token/cookie file for test-catalog.')
    parser.add_argument('-w', '--wipe', default=False, action='store_true',
                        help='Wipe the remote database completely.')
    return parser.parse_args()


def wipe_bugs_database(client, dryrun=True):
    remote_db = client.get_bug_info(force_refresh=True)
    for bugno in remote_db['bugs']:
        print("\nDeleting {} from database.".format(bugno))
        if not dryrun:
            client.delete_bug_info(bugno)


def get_new_or_bugs_to_edit(local_db, remote_db):
    orphan_bugs = []
    altered_bugs = []
    variable = [u'category', u'affects', u'description']
    for remote_bugno, remote_data in remote_db['bugs'].items():
        if remote_bugno in local_db['bugs']:
            # Find out which bugs have changed so we only upload those:
            local_data = local_db['bugs'][remote_bugno]
            jobs = [key for key in remote_data.keys() if key not in variable]
            different = False
            for job in jobs:
                if local_data[job] != remote_data[job]:
                    different = True
            if different:
                altered_bugs.append(remote_bugno)
        else:
            # Find any bugs in the remote_db if they aren't in the local_db:
            orphan_bugs.append((remote_bugno, remote_data))

    # Find any bugs that are in local_db that aren't in remote_db:
    new_bugs = [local_bugno for local_bugno, jnk in local_db['bugs'].items()
                if local_bugno not in remote_db['bugs']]
    altered_bugs.extend(new_bugs)
    return (altered_bugs, orphan_bugs)


def delete_orphan_bugs(client, db_location, orphan_bugs, force, dryrun=True):
    """Delete the bugs from the remote_db if they aren't in the local_db"""
    if orphan_bugs != []:
        print()
        print("The following bugs are in the database but not in {}:"
              .format(db_location))
        pprint([str(bugs[0]) for bugs in orphan_bugs])

        if force:
            confirmed = 'y'
        else:
            rm_orphans = raw_input("Delete orphan bugs? [y/N]").lower()
            if rm_orphans == 'y':
                confirmed = raw_input("Are you sure? [y/N]").lower()
        if confirmed == 'y':
            for rm_bug in orphan_bugs:
                print("\nDeleting {} from database.".format(rm_bug[0]))
                if not dryrun:
                    client.delete_bug_info(rm_bug[0])


def add_new_or_edit_existing_bugs(client, remote_db, local_db, altered_bugs,
                                  dryrun=True):
    """Add new bugs, and/or delete and reupload any altered bugs"""
    for bugno in altered_bugs:
        editing_bug = False
        data = local_db['bugs'][bugno]
        if 'description' in data:
            del data['description']
        if 'category' in data:
            del data['category']
        if bugno in remote_db['bugs']:
            editing_bug = True
            if not dryrun:
                client.delete_bug_info(bugno)
        for names, file_regex in data.items():
            for count, entry in enumerate(file_regex):
                first = True
                for file_, regexes in entry.items():
                    boolean = 'and'
                    if count > 0 and first:
                        boolean = 'or'
                    if isinstance(regexes['regexp'], str):
                        regexes['regexp'] = [regexes['regexp']]
                    for reg in regexes['regexp']:
                        if reg:
                            if editing_bug:
                                msg = "\nAmending {0} in database:"
                            else:
                                msg = "\nAdding {0} to database:"
                            msg += "\n({0}, {1}, {2}, {3}, {4})"
                            print(msg.format(bugno, names, file_, reg,
                                  boolean))
                            if not dryrun:
                                client.add_bug_info(
                                    bugno,
                                    names,
                                    file_,
                                    reg,
                                    boolean
                                )
                            first = False
                            boolean = 'and'


def update_bugs_database(client, db_location, force=False, dryrun=True):
    local_db = yaml.load(open(db_location))
    remote_db = client.get_bug_info(force_refresh=True)
    altered_bugs, orphan_bugs = get_new_or_bugs_to_edit(local_db, remote_db)
    delete_orphan_bugs(client, db_location, orphan_bugs, force)
    add_new_or_edit_existing_bugs(client, remote_db, local_db, altered_bugs)
    # last force_refresh is used to drop the cache from the server and reload
    return client.get_bug_info(force_refresh=True)


def main():
    args = parse()

    cookie = json.load(open(args.token))
    client = tc_client(endpoint=args.endpoint, cookies=cookie)
    if args.wipe:
        wipe_bugs_database(client)
    if args.dryrun:
        print("\n***Dry-run: No data will be written to database.***\n")
    update_bugs_database(client, args.database, args.force, args.dryrun)
    print


if __name__ == '__main__':
    main()
