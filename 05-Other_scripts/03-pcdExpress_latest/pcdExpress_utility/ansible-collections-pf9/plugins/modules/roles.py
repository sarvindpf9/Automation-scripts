import json
from ansible.module_utils.basic import AnsibleModule
import requests
from ansible_collections.pf9.pcd.plugins.module_utils.helper import PCDConn


class PCDRolesConfigModule(AnsibleModule):

    def __init__(self):
        self.argument_spec = dict(
            state=dict(default='present', choices=['absent', 'present']),
            mgmt_url=dict(type='str', required=True),
            token=dict(type='str', required=True),
            host_id=dict(type='str', required=True),
            # list of uber roles ('image-library', 'hypervisor', 'persistent-storage')
            roles=dict(type='list', required=True),
            persistent_storage=dict(type='dict', required=False),
            hostconfig=dict(type='str', required=True)
        )
        self.supports_check_mode = True

        super(PCDRolesConfigModule, self).__init__(argument_spec=self.argument_spec,
                                                   supports_check_mode=self.supports_check_mode)

    # Match and fetch hostconfig ID
    def config_id(self, src, target):
        for config in src:
            if config['name'] == target:
                # print("print name of config: {config['name']}")
                return config['id']
        return None

    def run(self):
        state = self.params['state']
        roles = self.params['roles']
        hostconfig = self.params['hostconfig']
        mgmt_url = self.params['mgmt_url']
        host_id = self.params['host_id']
        token = self.params['token']
        changed = False

        result = dict(
            changed=False,
            original_config='',
            new_config='',
            persistent_storage=None
        )

        if self.check_mode:
            self.exit_json(**result)

        self.persistent_storage = None
        print(f"Currently supplied roles: {roles}")

        if "persistent-storage" in roles:
            print("persistent-storage' role detected")
            persistent_storage_param = self.params.get("persistent_storage")
            #persistent_storage_param = self.persistent_storage

            if isinstance(persistent_storage_param, dict) and "backends" in persistent_storage_param:
                #self.persistent_storage = persistent_storage_param["backends"]
                self.persistent_storage = persistent_storage_param
                print(f"Extracted persistent storage dict: {self.persistent_storage}")
            #elif isinstance(persistent_storage_param, list):
            #    self.persistent_storage = persistent_storage_param
            #    print(f"Extracted persistent storage list: {self.persistent_storage}")
            else:
                self.fail_json(msg="Invalid persistent_storage format. Expected a dictionary with 'backends' list.")

            #print(f"Extracted persistent storage backends: {self.persistent_storage}")
            print(f"Storage backends in JSON format: {json.dumps(self.persistent_storage, indent=2)}")

        result['persistent_storage'] = self.persistent_storage

        # get hostconfig ID
        pcd = PCDConn(mgmt_url, token)
        hostconfig_endpoint_url = mgmt_url + 'resmgr/v2/hostconfigs'
        current_configs = {}
        response = pcd.get(hostconfig_endpoint_url)
        current_configs = response.json()
        hostconfig_id = self.config_id(current_configs, hostconfig)
        print(f"whats the hostconfig ID: {hostconfig_id}")
        if hostconfig_id is None:
            self.fail_json(msg='Hostconfig not found', **result)

        # URLs for the resources
        hostconfig_assoc_url = mgmt_url + "resmgr/v2/hosts/" + \
            host_id + "/hostconfig" + hostconfig_id
        hosts_endpoint_url = mgmt_url + "resmgr/v2/hosts/" + host_id
        # modify_roles_endpoint_url = mgmt_url + "resmgr/v2/hosts/" + host_id + f"/{roles}"
        modify_roles_endpoint_url = " "

        # Get hosts details for comparision:
        response = pcd.get(hosts_endpoint_url)
        current_hosts_details = response.json()
        # get the ID only if the hosts list has entries for comparison
        if current_hosts_details is None:
            self.fail_json(
                msg=f'No hosts found. Onboard the nodes first before applying PCD roles', **result)
        consumed_hostconfig = current_hosts_details.get('hostconfig_id')

        # Check and build roles lists
        uber_roles = [{'role': 'image-library', 'sub_roles': ['pf9-glance-role']},
                      {'role': 'hypervisor', 'sub_roles': ['pf9-ceilometer', 'pf9-ha-slave',
                                                           'pf9-neutron-base', 'pf9-neutron-ovn-controller',
                                                           'pf9-neutron-ovn-metadata-agent', 'pf9-ostackhost-neutron']},
                      {'role': 'persistent-storage', 'sub_roles': ['pf9-cindervolume-base']}]

        current_sub_roles = current_hosts_details.get('roles')
        current_uber_roles = set()
        for role in current_sub_roles:
            for uber_role in uber_roles:
                if role in uber_role['sub_roles']:
                    current_uber_roles.add(uber_role['role'])
        print(f"List of Current Uber roles assigned to host: {current_uber_roles}")

        # Apply hostconfig only if not set earlier on the host
        if consumed_hostconfig != hostconfig_id:
            try:
                response = pcd.get(hosts_endpoint_url)
                if host_id is not None:
                    hostconfig_assoc_url = mgmt_url + "/resmgr/v2/hosts/" + \
                        host_id + "/hostconfig" + f"/{hostconfig_id}"
                    print(f"get the url value: {hostconfig_assoc_url}")
                    hostconfig_response = pcd.put(hostconfig_assoc_url, {})
                    if hostconfig_response.status_code == 200:
                        changed = True
                    elif hostconfig_response.status_code == 409:
                        changed = False
            except requests.exceptions.RequestException as e:
                print(f"Warning: Failed to apply host config: {e}")
                changed = False
        else:
            print("The hostconfig ID is already associated with the host.. ")

        # Check and apply or remove only those roles that are not or applied on the nodes.
        pcd = PCDConn(mgmt_url, token)
        if state == 'absent':
            for role in roles:
                if role in current_uber_roles:
                    modify_roles_endpoint_url = mgmt_url + \
                        "/resmgr/v2/hosts/" + host_id + "/roles" + f"/{role}"
                    response = pcd.delete(modify_roles_endpoint_url)
                    if response.status_code == 200:
                        changed = True
                        result = {
                            "changed": changed,
                            "msg": f"Role removed successfully"
                        }
                else:
                    result = {
                        "changed": changed,
                        "msg": f" no roles currently applied on the hosts.."
                    }
            self.exit_json(**result)
        elif state == 'present':
            for role in roles:
                modify_roles_endpoint_url = f"{mgmt_url}/resmgr/v2/hosts/{host_id}/roles/{role}"
                if role in current_uber_roles:
                   print(f"Skipping role '{role}' as it is already applied.")
                   result = {
                       "changed": False,
                       "msg": f"Role '{role}' is already applied. No changes made."
                   }
                   continue
                if role == "persistent-storage" and self.persistent_storage:
                    #storage_payload = json.dumps(self.persistent_storage)
                    #headers = {
                    #    'Content-Type': 'application/json',
                    #    'X-Auth-Token': token,
                    #}
                    #response = requests.put(
                    #    modify_roles_endpoint_url, data=storage_payload, headers=headers)
                    response = pcd.put(modify_roles_endpoint_url, self.persistent_storage)
                else:
                    response = pcd.put(modify_roles_endpoint_url, {})
                if response.status_code == 200:
                    changed = True
                    result = {
                        "changed": changed,
                        "msg": f"Role '{role}' applied successfully."
                    }
                elif response.status_code == 401:
                    changed = False
                    result = {
                        "changed": changed,
                        "msg": f"Role '{role}' not applied due to authentication error."
                    }
                elif response.status_code == 500:
                    changed = False
                    result = {
                        "changed": changed,
                        "msg": f"Role '{role}' not applied due to internal error."
                    }
                elif role in ["node_onboard", "node-onboard"]:
                    print(f"Skipping non-PCD role '{role}'")
                    continue  # Skip non-PCD roles
                else:
                    changed = False
                    result = {
                        "changed": changed,
                        "msg": f"Role '{role}' is already applied. No changes made."
                    }
            self.exit_json(**result)
        else:
            self.fail_json(msg=f'{state} is Invalid value.', **result)

        if changed:
            result['changed'] = True
            result['new_config'] = json.dumps(roles)

        self.exit_json(**result)


def main():
    module = PCDRolesConfigModule()
    module.run()


if __name__ == '__main__':
    main()
