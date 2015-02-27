import os
import yaml
from doberman.common.common import Common


class FileParser(Common):
    """
    """

    def __init__(self, path, filename):
        self.status = []
        self.filename = filename
        self.path = path
        self.path_to_file = os.path.join(self.path, self.filename)
        self._process_data()

    def _extract_information(self, ftype=None):
        try:
            with open(self.path_to_file, "r") as f:
                if ftype == 'yaml':
                    return yaml.load(f)
                else:
                    return f.read()
        except IOError, e:
            msg = "Problem reading {} from {} ({})"
            self.status.append(msg.format(self.filename, self.path, e[1]))
            return

    def _process_data(self):
        if self.filename =='console.txt':
            self._process_console_data()
        if self.filename =='oil_nodes':
            self._process_oil_nodes_data()
        if self.filename =='juju_status.yaml':
            self._process_juju_status_data()

    def _process_console_data(self):
        self.data = self._extract_information('txt')

        # Set up defaults in case missing console.txt:
        if 'bsnode' not in self.__dict__:
            self.bsnode = {}
        if 'openstack release' not in self.bsnode:
            self.bsnode["openstack release"] = "Unknown"
        if 'jenkins' not in self.bsnode:
            self.bsnode["jenkins"] = "Unknown"
        msg = "Unable to extract {} from {}."

        try:
            self.bsnode['openstack release'] = \
                self.data.split('OPENSTACK_RELEASE=')[1].split('\n')[0]
        except:
            self.status.append(msg.format('openstack release', 'console'))

        try:
            self.bsnode['jenkins'] = \
                self.data.split('\n')[1].split(' in workspace /var/lib/')[0]
        except:
            self.status.append(msg.format('jenkins', 'console'))

    def _process_oil_nodes_data(self):
        self.data = self._extract_information('yaml')

        # Set up defaults in case missing oil_nodes:
        self.oil_nodes = {}

        if self.data:
            for key in self.data['oil_nodes'][0].keys():
                [self.dictator(self.oil_nodes, key, node[key]) for node in
                 self.data['oil_nodes']]
            
            '''
            if self.oil_nodes:
                try:
                    node_idx = self.oil_nodes['host'].index(host_name)
                    hardware = [hw.split('hardware-')[1] for hw in
                                self.oil_nodes['tags'][node_idx]
                                if 'hardware-' in hw]
                    slave = ", ".join([str(slv) for slv in
                                      self.oil_nodes['tags'][node_idx]
                                      if 'slave-' in slv])
            '''
        else:
            self.status.append(msg.format('info', 'oil_nodes'))

    def _process_juju_status_data(self):
        self.data = self._extract_information('yaml')

        # Set up defaults in case missing juju_status.yaml:
        default_message = "Unknown (absent juju_status.yaml)"

        if 'bsnode' not in self.__dict__:
            self.bsnode = {}
        if 'machine' not in self.bsnode:
            self.bsnode["machine"] = "Unknown"
        if 'state' not in self.bsnode:
            self.bsnode["state"] = "Unknown"

        self.oil_df = {"vendor": default_message,
                       "node": default_message,
                       "service": default_message,
                       "charm": default_message,
                       "ports": default_message,
                       "state": default_message,
                       "slaves": default_message}

        # Get info for bootstrap node (machine 0):
        try:
            machine_info = self.data['machines']['0']
        except:
            machine_info = None
        if machine_info:
            m_name = machine_info.get('dns-name', 'Unknown')
            m_os = machine_info.get('series', 'Unknown')
            machine = m_os + " running " + m_name
            state = machine_info.get('agent-state', 'Unknown')
            self.bsnode['machine'] = machine
            self.bsnode['state'] = state

            row = 0
            for service in self.data['services']:
                serv = self.data['services'][service]
                charm = serv['charm'] if 'charm' in serv else 'Unknown'
                if 'units' in serv:
                    units = serv['units']
                else:
                    units = {}
                    self.dictator(self.oil_df, 'node', 'N/A')
                    self.dictator(self.oil_df, 'service', 'N/A')
                    self.dictator(self.oil_df, 'vendor', 'N/A')
                    self.dictator(self.oil_df, 'charm', charm)
                    self.dictator(self.oil_df, 'ports', 'N/A')
                    self.dictator(self.oil_df, 'state', 'N/A')
                    self.dictator(self.oil_df, 'slaves', 'N/A')

                for unit in units:
                    this_unit = units[unit]
                    ports = ", ".join(this_unit['open-ports']) if 'open-ports' \
                        in this_unit else "N/A"
                    machine_no = this_unit['machine'].split('/')[0]
                    host_name = (this_unit['public-address'] if 'public-address' in
                                 this_unit else 'Unknown')
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
                    self.dictator(self.oil_df, 'node', machine)
                    self.dictator(self.oil_df, 'service', unit)
                    self.dictator(self.oil_df, 'vendor', ', '.join(hardware))
                    self.dictator(self.oil_df, 'charm', charm)
                    self.dictator(self.oil_df, 'ports', ports)
                    self.dictator(self.oil_df, 'state', state)
                    self.dictator(self.oil_df, 'slaves', slave)
                    row += 1
            else:  # Oh look, Python lets you put elses after for statements...
                self.dictator(self.oil_df, 'node', 'N/A')
                self.dictator(self.oil_df, 'service', 'N/A')
                self.dictator(self.oil_df, 'vendor', 'N/A')
                self.dictator(self.oil_df, 'charm', 'N/A')
                self.dictator(self.oil_df, 'ports', 'N/A')
                self.dictator(self.oil_df, 'state', 'N/A')
                self.dictator(self.oil_df, 'slaves', 'N/A')












































        #juju_status, self.yaml_dict = self.get_yaml(juju_status_location,
        #                                            self.yaml_dict)

'''

parser = {'console.txt': {'url': 'https://sprint-rest.turnitin.com/',
                          'find_user_by_email_url_suffix': "user/find_by_email?email=",
                          'find_user_by_email_postprocessor':
                          lambda r: int(json.loads(r.text)['user'][0]['id'].split('/')[-1]),
                          'create_class_url_suffix': "class/",
                          'create_class_postprocessor': lambda r: json.loads(r.text)['class'],
                          'create_user_url_suffix': "user/",
                          'create_user_postprocessor': lambda r: json.loads(r.text)['user'],
                          'create_assignment_url_suffix': "assignment/",
                          'create_assignment_postprocessor': lambda r: json.loads(r.text)['assignment'],
                          'destroy_class_url_suffix': "class/",
                          'get_assignment_details_url_suffix': "assignment/",
                          'error_postprocessor':
                          lambda r: (json.loads(r.text)['error'] if 'text' in r.__dict__.keys() else str(r.status_code) +
                                     " error (" + r.reason + ") during " + r.request.method + " request to " + r.request.url),
                          }
         }

'''
