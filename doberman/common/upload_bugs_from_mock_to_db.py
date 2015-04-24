#!/usr/bin/python

from test_catalog.client.api import TCClient as tc_client
import argparse
import json
import yaml


DEFAULT_DB = 'samples/mock_database.yml'
DEFAULT_TOKEN = 'test-catalog-auth.json'
DEFAULT_ENDPOINT = 'https://oil.canonical.com/api/'

def parse():
    parser = argparse.ArgumentParser(
        description='Upload bugs to remote database.'
    )
    parser.add_argument('-e', '--endpoint', default=DEFAULT_ENDPOINT,
                        help='Remote test-catalog URL for database interface.')
    parser.add_argument('-t', '--token', default=DEFAULT_TOKEN,
                        help='Token/cookie file for test-catalog.')
    parser.add_argument('-d', '--database', default=DEFAULT_DB,
                        help='Location of yaml to upload to the database.')
    parser.add_argument('-w', '--wipe', default=False, action='store_true',
                        help='Wipe the remote database completely.')
    return parser.parse_args()


def wipe_bugs_database(client):
    remote_db = client.get_bug_info(force_refresh=True)
    for bugno in remote_db['bugs']:
        client.delete_bug_info(bugno)


def update_bugs_database(client, db_location):
    local_db = yaml.load(open(db_location))
    remote_db = client.get_bug_info(force_refresh=True)

    for bugno, data in local_db['bugs'].items():
        if 'description' in data:
            del data['description']
        if 'category' in data:
            del data['category']
        if bugno in remote_db['bugs']:
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
                            print(bugno, names, file_, reg, boolean)
                            client.add_bug_info(
                                bugno,
                                names,
                                file_,
                                reg,
                                boolean
                            )
                            first = False
                            boolean = 'and'

    # last force_refresh is used to drop the cache from the server and reload
    return client.get_bug_info(force_refresh=True)


def main():
    args = parse()

    cookie = json.load(open(args.token))
    client = tc_client(endpoint=args.endpoint, cookies=cookie)
    if args.wipe:
        wipe_bugs_database(client)
    update_bugs_database(client, args.database)


if __name__ == '__main__':
    main()
