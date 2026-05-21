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

    def _compare_configs(self, current_config, requested_config):
        updatable_fields = [
            'name', 'description', 'spec', 'metadata', 
            'config', 'parameters', 'template', 'version'
        ]
        
        for field in updatable_fields:
            if field in requested_config:
                current_value = current_config.get(field)
                requested_value = requested_config.get(field)
                if current_value != requested_value:
                    self.module.debug(f"Field '{field}' differs: current={current_value}, requested={requested_value}")
                    return False
        return True
    
    def _extract_updatable_config(self, requested_config):
        """Extract only the fields that should be sent in update requests"""
        # Some APIs require excluding certain fields during updates
        exclude_fields = ['id', 'created_at', 'updated_at', 'created_by', 'uuid']
        
        filtered_config = {}
        for key, value in requested_config.items():
            if key not in exclude_fields:
                filtered_config[key] = value
                
        return filtered_config

    def run(self):
        state = self.params['state']
        requested_config = self.params['config']
        mgmt_url = self.params['mgmt_url']
        token = self.params['token']
        changed = False

        result = dict(
            changed=False,
            original_config='',
            new_config='',
            message=''
        )

        if self.check_mode:
            result['message'] = 'Check mode: would have processed blueprint config'
            self.exit_json(**result)

        pcd = PCDConn(mgmt_url, token)
        config_endpoint_url = mgmt_url + '/resmgr/v2/blueprint'
        config_name = requested_config['name']
        config_url = config_endpoint_url + '/' + config_name

        # Delete the configuration if state is absent
        if state == 'absent':
            headers = {
                'Content-Type': 'application/json',
                'X-Auth-Token': f'{token}',
            }
            # First check if it exists
            response = requests.get(config_url, headers=headers)
            if response.status_code == 200:
                # It exists, so delete it
                response = pcd.delete(config_url)
                if response.status_code in [200, 204]:
                    result['changed'] = True
                    result['message'] = f'Blueprint {config_name} deleted successfully'
                else:
                    self.fail_json(msg=f'Failed to delete blueprint: {response.status_code} - {response.text}')
            elif response.status_code == 404:
                result['message'] = f'Blueprint {config_name} already absent'
            else:
                self.fail_json(msg=f'Error checking blueprint existence: {response.status_code} - {response.text}')
            
            self.exit_json(**result)

        #present state
        headers = {
            'Content-Type': 'application/json',
            'X-Auth-Token': f'{token}',
        }
        
        response = requests.get(config_url, headers=headers)
        
        if response.status_code == 404:
            # Create the configuration if it does not exist
            filtered_config = self._extract_updatable_config(requested_config)
            response = pcd.post(config_endpoint_url, filtered_config)
            if response.status_code == 201:
                result['changed'] = True
                result['new_config'] = json.dumps(filtered_config)
                result['message'] = f'Blueprint {config_name} created successfully'
            else:
                self.fail_json(msg=f'Failed to create blueprint: {response.status_code} - {response.text}')
            self.exit_json(**result)
        
        elif response.status_code == 200:
            # Configuration exists, check if update is needed
            current_config = response.json()
            result['original_config'] = json.dumps(current_config)

            # Compare configurations using only updatable fields
            if not self._compare_configs(current_config, requested_config):
                # Update needed
                filtered_config = self._extract_updatable_config(requested_config)
                response = pcd.put(config_url, filtered_config)
                if response.status_code == 200:
                    changed = True
                    result['new_config'] = json.dumps(filtered_config)
                    result['message'] = f'Blueprint {config_name} updated successfully'
                else:
                    self.fail_json(msg=f'Failed to update blueprint: {response.status_code} - {response.text}')
            else:
                result['message'] = f'Blueprint {config_name} already up to date'

        else:
            self.fail_json(msg=f'Unexpected response when checking blueprint: {response.status_code} - {response.text}')

        if changed:
            result['changed'] = True

        self.exit_json(**result)

def main():
    module = PCDBlueprintConfigModule()
    module.run()

if __name__ == '__main__':
    main()