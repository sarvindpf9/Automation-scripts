#!/usr/bin/python

import json
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.pf9.pcd.plugins.module_utils.helper import PCDConn

class PCDHostConfigModule(AnsibleModule):

    def __init__(self):
        self.argument_spec=dict(
            state=dict(default='present', choices=['absent', 'present']),
            mgmt_url=dict(type='str', required=True),
            token=dict(type='str', required=True),
            config=dict(type='dict', required=True)
        )
        self.supports_check_mode=True

        super(PCDHostConfigModule, self).__init__(argument_spec=self.argument_spec,
                                              supports_check_mode=self.supports_check_mode)

    def config_id(self, src, target):
        for config in src:
            if config['name'] == target['name']:
                return config['id']
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
        hostconfig_endpoint_url = mgmt_url + '/resmgr/v2/hostconfigs'

        current_configs = {}
        response = pcd.get(hostconfig_endpoint_url)
        current_configs = response.json()

        # if state is absent, delete the hostconfig
        if state == 'absent':
            # find the hostconfig id from the current configs
            hostconfig_id = self.config_id(current_configs, requested_config)
            if hostconfig_id is None:
                self.fail_json(msg='Hostconfig not found', **result)

            hostconfig_url = hostconfig_endpoint_url + '/' + hostconfig_id
            response = pcd.delete(hostconfig_url)
            if response.status_code == 204:
                changed = True
        else:
            hostconfig_id = self.config_id(current_configs, requested_config)
            # if hostconfig does not exist, create it
            if hostconfig_id is None:
                response = pcd.post(hostconfig_endpoint_url, requested_config)
                if response.status_code == 201:
                    changed = True
            else:
                # get the current hostconfig and compare it with the requested hostconfig
                hostconfig_url = hostconfig_endpoint_url + '/' + hostconfig_id
                response = pcd.get(hostconfig_url)
                current_config = response.json()
                result['original_config'] = json.dumps(current_config)

                current_config.pop('id', None)
                if current_config != requested_config:
                    response = pcd.put(hostconfig_url, requested_config)
                    if response.status_code == 200:
                        changed = True

        if changed:
            result['changed'] = True
            result['new_config'] = json.dumps(requested_config)

        self.exit_json(**result)

def main():
    module = PCDHostConfigModule()
    module.run()

if __name__ == '__main__':
    main()
