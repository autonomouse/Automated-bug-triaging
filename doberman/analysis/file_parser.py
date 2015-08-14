import os
import yaml
from doberman.common.base import DobermanBase


class FileParser(DobermanBase):
    """
    An object to extract relevant information from the following file-types
    currently used in OIL:
       - console.txt
       - oil_nodes
       - juju_status.yaml
    """

    def __init__(self, path, job):
        self.status = []
        self.filenames = ['{}_console.txt'.format(job),
                          'oil_nodes',
                          'juju_status.yaml']
        self.path = path
        self.extracted_info = {}
        self._process_data()
        # TODO: Pull data in from dpkg file (this is a pipeline_start job)
        # TODO: Then include maas logs/other plugin files (write them first)

    def _extract_information(self, ftype=None):
        try:
            with open(self.path_to_file, "r") as f:
                if ftype == 'yaml':
                    return yaml.load(f)
                else:
                    return f.read()
        except IOError as e:
            msg = "Problem reading {} from {} ({})"
            filename = os.path.basename(self.path_to_file)
            self.status.append(msg.format(filename, self.path, e[1]))
            return

    def _process_data(self):
        for filename in self.filenames:
            self.path_to_file = os.path.join(self.path, filename)
            if 'console.txt' in filename:
                self._process_console_data()
            if filename == 'oil_nodes':
                self._process_oil_nodes_data()
            if filename == 'juju_status.yaml':
                self._process_juju_status_data()

    def _process_console_data(self):
        self.data = self._extract_information('txt')

        # Set up defaults in case missing console.txt:
        if 'bsnode' not in self.extracted_info:
            self.extracted_info['bsnode'] = {}
        if 'openstack release' not in self.extracted_info['bsnode']:
            self.extracted_info['bsnode']["openstack release"] = "Unknown"
        if 'jenkins' not in self.extracted_info['bsnode']:
            self.extracted_info['bsnode']["jenkins"] = "Unknown"
        msg = "Unable to extract {} from {}."

        if self.data and 'OPENSTACK_RELEASE=' in self.data:
            self.extracted_info['bsnode']['openstack release'] = \
                self.data.split('OPENSTACK_RELEASE=')[1].split('\n')[0]
        else:
            self.status.append(msg.format('openstack release', 'console'))

        if self.data and ' in workspace /var/lib/' in self.data:
            self.extracted_info['bsnode']['jenkins'] = \
                self.data.split('\n')[1].split(' in workspace /var/lib/')[0]
        else:
            self.status.append(msg.format('jenkins', 'console'))

    def _process_oil_nodes_data(self):
        self.data = self._extract_information('yaml')

        # Set up defaults in case missing oil_nodes:
        self.extracted_info['oil_nodes'] = {}

        if not self.data:
            msg = "Unable to extract {} from {}."
            self.status.append(msg.format('info', 'oil_nodes'))
            return

        for key in self.data['oil_nodes'][0].keys():
            [self.dictator(self.extracted_info['oil_nodes'], key, node[key])
             for node in self.data['oil_nodes']]

    def _process_juju_status_data(self):
        self.data = self._extract_information('yaml')

        # Set up defaults in case missing juju_status.yaml:
        default_message = "Unknown"

        if 'bsnode' not in self.extracted_info:
            self.extracted_info['bsnode'] = {}
        if 'machine' not in self.extracted_info['bsnode']:
            self.extracted_info['bsnode']["machine"] = "Unknown"
        if 'state' not in self.extracted_info['bsnode']:
            self.extracted_info['bsnode']["state"] = "Unknown"

        self.extracted_info['oil_df'] = {"vendor": [],
                                         "node": [],
                                         "service": [],
                                         "charm": [],
                                         "ports": [],
                                         "state": [],
                                         "slaves": []}

        # Get info for bootstrap node (machine 0):
        if not hasattr(self, 'data') or self.data is None:
            return
        if 'machines' not in self.data:
            return

        machine_info = self.data['machines'].get('0') if self.data else None

        if not machine_info:
            return

        m_name = machine_info.get('dns-name', 'Unknown')
        m_os = machine_info.get('series', 'Unknown')
        machine = m_os + " running " + m_name
        state = machine_info.get('agent-state', 'Unknown')
        self.extracted_info['bsnode']['machine'] = machine
        self.extracted_info['bsnode']['state'] = state

        row = 0
        for service in self.data['services']:
            serv = self.data['services'][service]
            charm = serv['charm'] if 'charm' in serv else 'Unknown'
            if 'units' in serv:
                units = serv['units']
            else:
                units = {}
                self.dictator(self.extracted_info['oil_df'], 'node', 'N/A')
                self.dictator(self.extracted_info['oil_df'], 'service', 'N/A')
                self.dictator(self.extracted_info['oil_df'], 'vendor', 'N/A')
                self.dictator(self.extracted_info['oil_df'], 'charm', charm)
                self.dictator(self.extracted_info['oil_df'], 'ports', 'N/A')
                self.dictator(self.extracted_info['oil_df'], 'state', 'N/A')
                self.dictator(self.extracted_info['oil_df'], 'slaves', 'N/A')

            for unit in units:
                this_unit = units[unit]
                ports = ", ".join(this_unit['open-ports']) if 'open-ports' \
                    in this_unit else "N/A"
                machine_no = this_unit['machine'].split('/')[0]
                machine_info = self.data['machines'][machine_no]

                if 'hardware' in machine_info:
                    hardware = [hw.split('hardware-')[1] for hw in
                                machine_info['hardware'].split('tags=')
                                [1].split(',') if 'hardware-' in hw]
                    slave = ", ".join([str(slv) for slv in machine_info
                                       ['hardware'].split('tags=')[1]
                                       .split(',') if 'slave' in slv])
                else:
                    hardware = ['Unknown']
                    slave = 'Unknown'

                if '/' in this_unit['machine']:
                    container_name = this_unit['machine']
                    container = machine_info['containers'][container_name]
                elif 'containers' in machine_info:
                    if len(machine_info['containers'].keys()) == 1:
                        container_name = machine_info['containers'].keys()[0]
                        container = machine_info['containers'][container_name]
                    else:
                        # TODO: Need to find a way to identify
                        # which container is being used here:
                        container = []
                else:
                    container = []

                m_name = machine_info.get('dns-name', "")
                state = machine_info.get('agent-state', '')
                state = state + ". " if state else state + ""
                state += container['agent-state-info'] + ". " \
                    if 'agent-state-info' in container else ''
                state += container['instance-id'] if 'instance-id' in \
                    container else ''
                m_ip = " (" + container['dns-name'] + ")" \
                       if 'dns-name' in container else ""
                machine_id = m_name + m_ip
                machine = machine_id if machine_id else "Unknown"
                self.dictator(self.extracted_info['oil_df'], 'node', machine)
                self.dictator(self.extracted_info['oil_df'], 'service', unit)
                self.dictator(self.extracted_info['oil_df'], 'vendor',
                              ', '.join(hardware))
                self.dictator(self.extracted_info['oil_df'], 'charm', charm)
                self.dictator(self.extracted_info['oil_df'], 'ports', ports)
                self.dictator(self.extracted_info['oil_df'], 'state', state)
                self.dictator(self.extracted_info['oil_df'], 'slaves', slave)
                row += 1

        for key in self.extracted_info['oil_df']:
            if not self.extracted_info['oil_df'][key]:
                self.dictator(self.extracted_info['oil_df'], key,
                              default_message)
