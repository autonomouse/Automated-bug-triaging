#!/usr/bin/python

from test_catalog.client.api import TCClient as tc_client
import yaml
import json

DEFAULT_DB_LOCATION = '/usr/share/doberman/samples/mock_database.yml'
DEFAULT_COOKIE_LOCATION = '/etc/oil-ci/test-catalog-auth.json'
DEFAULT_ENDPOINT = 'https://oil.canonical.com/api/'


def update_bugs_database(db_location, cookie_location, endpoint):
    local_db = yaml.load(open(db_location))
    cookie = json.load(open(cookie_location))
    client = tc_client(endpoint=endpoint, cookies=cookie)

    remote_db = {'bugs': []}
    try:
        remote_db = client.get_bug_info(force_refresh=True)
    except:
        pass

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

    return client.get_bug_info(force_refresh=True)


def main():
    update_bugs_database(
        DEFAULT_DB_LOCATION,
        DEFAULT_COOKIE_LOCATION,
        DEFAULT_ENDPOINT
    )


if __name__ == '__main__':
    main()
