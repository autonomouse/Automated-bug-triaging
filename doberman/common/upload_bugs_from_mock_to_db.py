
from test_catalog.client.api import TCClient as tc_client
import yaml
import json

db = yaml.load(open('/usr/share/doberman/samples/mock_database.yml'))

cook = json.load(open('test-catalog-auth.json'))

client = tc_client(endpoint='https://oil.canonical.com/api/', cookies=cook)

#db = client.get_bug_info()
#thing = \
#"""
#  "1386679":
#    category: None
#    description: "Prodstack: storage backend relation joined"
#    pipeline_deploy:
#      -
#        "console.txt":
#            regexp:
#            - "unit. cinder-vnx... machine.  agent-state. error details. hook failed...storage-backend-relation-joined"
#      -
#        "juju_status.yaml":
#            regexp:
#            - "hook failed...storage.backend.relation.joined.+for cinder-vnx.storage.backend"
#            - "hook failed...storage.backend.relation.joined.+for cinder-vnx.storage.backend2"
#        "console.txt":
#            regexp:
#            - "udetails. hook failed...storage-backend-relation-joined"
#"""
#db = {'bugs': yaml.load(thing)}

for bugno, data in db['bugs'].items():
    del data['description']
    del data['category']
    for names, file_regex in data.items():
        for count, entry in enumerate(file_regex):
            first = True
            for file, regexes in entry.items():
                boolean = 'and'
                if count > 0 and first:
                    boolean = 'or'
                if isinstance(regexes['regexp'], str):
                    regexes['regexp'] = [regexes['regexp']]
                for reg in regexes['regexp']:
                    if reg:
                        print(bugno, names, file, reg, boolean)
                        client.add_bug_info(bugno, names, file, reg, boolean)
                        first = False
                        boolean = 'and'

#print client.get_bug_info()

