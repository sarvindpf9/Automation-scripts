#!/usr/bin/python

import json
import requests
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.pf9.pcd.plugins.module_utils.helper import PCDConn

class PCDBlueprintConfigModule(AnsibleModule):

    def __init__(self):
        self.argument_spec=dict(
            state=dict(default='present', choices=['absent', 'present']),
            mgmt_url=dict(type='str', required=True),
            token=dict(type='str', required=True),
            config=dict(type='dict', required=True)
        )
        self.supports_check_mode=True

        super(PCDBlueprintConfigModule, self).__init__(argument_spec=self.argument_spec,
                                              supports_check_mode=self.supports_check_mode)

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
        config_endpoint_url = mgmt_url + '/resmgr/v2/blueprint'
        config_name = requested_config['name']
        config_url = config_endpoint_url + '/' + config_name

        # Delete the configuration if state is absent
        if state == 'absent':
            response = pcd.delete(config_url)
            if response.status_code == 200:
                result['changed'] = True
            self.exit_json(**result)

        # Create the configuration if it does not exist
        headers = {
            'Content-Type': 'application/json',
            'X-Auth-Token': f'{token}',
        }
        response = requests.get(config_url, headers=headers)
        if response.status_code == 404:
            response = pcd.post(config_endpoint_url, requested_config)
            if response.status_code == 201:
                result['changed'] = True
            self.exit_json(**result)

        # Update the configuration if it exists
        current_config = response.json()
        result['original_config'] = json.dumps(current_config)

        if current_config != requested_config:
            response = pcd.put(config_url, requested_config)
            if response.status_code == 200:
                changed = True

        if changed:
            result['changed'] = True
            result['new_config'] = json.dumps(requested_config)

        self.exit_json(**result)

def main():
    module = PCDBlueprintConfigModule()
    module.run()

if __name__ == '__main__':
    main()
