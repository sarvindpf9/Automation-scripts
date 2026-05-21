#!/usr/bin/python
import json
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.pf9.pcd.plugins.module_utils.helper import PCDConn


class PCDNetworkConfigModule(AnsibleModule):

    keys_to_ignore = ['id', 'tenant_id', 'created_at', 'updated_at', 'status'
                      'revision_number', 'tags', 'availability_zones', 'availability_zone_hints',
                      'ipv4_address_scope', 'ipv6_address_scope', 'provider:physical_network',
                      'provider:network_type', 'provider:segmentation_id'
                      ]

    def __init__(self):
        self.argument_spec = dict(
            state=dict(default='present', choices=['absent', 'present']),
            mgmt_url=dict(type='str', required=True),
            token=dict(type='str', required=True),
            config=dict(type='dict', required=True)
        )
        self.supports_check_mode = True

        super(PCDNetworkConfigModule, self).__init__(
            argument_spec=self.argument_spec, supports_check_mode=self.supports_check_mode)

    def config_id(self, src, target):
        for config in src.get('networks', []):
            if config.get('name') == target.get('network', {}).get('name'):
                print(f"print name of config: {config.get('id')}")
                return config.get('id')
        return None

    def run(self):
        state = self.params['state']
        requested_config = self.params['config']
        mgmt_url = self.params['mgmt_url']
        token = self.params['token']
        changed = False

        result = dict(
            changed=False,
            original_config='',
            new_config=''
        )

        if self.check_mode:
            self.exit_json(**result)

        pcd = PCDConn(mgmt_url, token)
        network_endpoint_url = mgmt_url + '/neutron/v2.0/networks'

        current_configs = {}
        response = pcd.get(network_endpoint_url)
        current_configs = response.json()

        # if state is absent, delete the network
        if state == 'absent':
            print(
                f"input current target name: {requested_config.get('network', {}).get('name')}")

            network_id = self.config_id(current_configs, requested_config)
            if network_id is None:
                self.fail_json(
                    msg='Network not found or already removed.', **result)

            network_url = network_endpoint_url + '/' + network_id
            response = pcd.delete(network_url)
            if response.status_code == 204:
                changed = True
        else:
            network_id = self.config_id(current_configs, requested_config)
            # if network does not exist, create it
            if network_id is None:
                response = pcd.post(network_endpoint_url, requested_config)
                if response.status_code == 201:
                    changed = True
            else:
                # get the current network and compare it with the requested network
                network_url = network_endpoint_url + '/' + network_id
                response = pcd.get(network_url)
                current_config = response.json()
                result['original_config'] = json.dumps(current_config)
                # print(f"The keys in current value is : {current_config.get('network', {})}")
                # print(f"The keys requested values are : {requested_config.get('network', {})}")
                current_config_data = current_config.get('network', {})
                requested_config_data = requested_config.get('network', {})

                # if the current network is different from the requested network, update it
                # otherwise, do nothing
                # when comparing, only compare the values of the requested network
                # that are in the current network

                keys_to_remove = [key for key in self.keys_to_ignore if key in requested_config_data]
                for key in keys_to_remove:
                    requested_config_data.pop(key, None)
                for key in requested_config_data.keys():
                    if key in current_config_data and current_config_data[key] != requested_config_data[key]:
                        requested_config['network'] = requested_config_data
                        response = pcd.put(network_url, requested_config)
                        if response.status_code == 200:
                            changed = True

        if changed:
            result['changed'] = True
            result['new_config'] = json.dumps(requested_config)

        self.exit_json(**result)


def main():
    module = PCDNetworkConfigModule()
    module.run()


if __name__ == '__main__':
    main()
