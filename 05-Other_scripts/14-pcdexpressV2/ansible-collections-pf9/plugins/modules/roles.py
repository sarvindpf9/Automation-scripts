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
            roles=dict(type='list', required=True),
            persistent_storage=dict(type='dict', required=False),
            hostcluster=dict(type='str', required=False),
            hostconfig=dict(type='str', required=True)
        )
        self.supports_check_mode = True

        super(PCDRolesConfigModule, self).__init__(argument_spec=self.argument_spec,
                                                   supports_check_mode=self.supports_check_mode)

    def config_id(self, src, target):
        for config in src:
            if config['name'] == target:
                return config['id']
        return None

    def run(self):
        params = self.params
        changed = False

        result = {
            'changed': False,
            'msg': '',
            'new_config': '',
        }
        if self.check_mode:
            self.exit_json(**result)

        mgmt_url = params['mgmt_url']
        token = params['token']
        host_id = params['host_id']
        roles = params['roles']
        hostconfig_name = params['hostconfig']
        hostcluster = params.get('hostcluster')
        persistent_storage = params.get('persistent_storage')

        pcd = PCDConn(mgmt_url, token)

        hostconfigs = pcd.get(mgmt_url + 'resmgr/v2/hostconfigs').json()
        hostconfig_id = self.config_id(hostconfigs, hostconfig_name)
        if hostconfig_id is None:
            self.fail_json(msg='Hostconfig not found', **result)

        host_info = pcd.get(mgmt_url + f"resmgr/v2/hosts/{host_id}").json()
        current_hostconfig = host_info.get('hostconfig_id')
        current_sub_roles = host_info.get('roles') or []

        uber_roles = {
            'image-library': {'pf9-glance-role'},
            'hypervisor': {
                'pf9-ceilometer', 'pf9-ha-slave', 'pf9-neutron-base',
                'pf9-neutron-ovn-controller', 'pf9-neutron-ovn-metadata-agent', 'pf9-ostackhost-neutron'
            },
            'persistent-storage': {'pf9-cindervolume-base'},
        }
        current_uber_roles = {
            role for role, subs in uber_roles.items()
            if set(current_sub_roles).intersection(subs)
        }

        if current_hostconfig != hostconfig_id:
            resp = pcd.put(
                f"{mgmt_url}resmgr/v2/hosts/{host_id}/hostconfig/{hostconfig_id}", {})
            if resp and resp.status_code == 200:
                changed = True
        if params['state'] == 'present':
            add_msgs = []
            for role in roles:
                if role in current_uber_roles:
                    add_msgs.append(f"Role '{role}' is already present. Skipped.")
                    continue
                url = f"{mgmt_url}resmgr/v2/hosts/{host_id}/roles/{role}"
                resp = None
                if role == 'hypervisor':
                    clusters = pcd.get(mgmt_url + 'resmgr/v2/clusters').json()
                    cluster = next((c for c in clusters if c['name'] == hostcluster), None)

                    if not cluster:
                        payload = {
                            "name": hostcluster,
                            "vmHighAvailability": {"enabled": True},
                            "autoResourceRebalancing": {
                                "enabled": True,
                                "rebalancingStrategy": "vm_workload_consolidation",
                                "rebalancingFrequencyMins": 20
                            },
                            "gpu": {"enabled": False, "mode": "passthrough"}
                        }
                        cl_resp = pcd.post(mgmt_url + "resmgr/v2/clusters/", payload)
                        if cl_resp and cl_resp.status_code in (200, 201):
                            changed = True
                            add_msgs.append(f"Cluster '{hostcluster}' created.")
                        else:
                            add_msgs.append(f"Failed to create cluster '{hostcluster}', status: {getattr(cl_resp, 'status_code', 'None')}")
                            continue
                        # re-fetch created cluster
                        clusters = pcd.get(mgmt_url + 'resmgr/v2/clusters').json()
                        cluster = next((c for c in clusters if c['name'] == hostcluster), None)

                    if cluster:
                        if host_id in (cluster.get('hostlist') or []):
                            add_msgs.append(f"Host already in cluster '{hostcluster}'. Skipped.")
                            continue
                        payload = {"hostcluster": hostcluster}
                        resp = pcd.put(url, payload)
                elif role == 'persistent-storage' and persistent_storage:
                    payload = dict(persistent_storage)
                    payload['hostconfig'] = hostconfig_name
                    resp = pcd.put(url, payload)
                elif role == 'image-library':
                    resp = pcd.put(url, {})
                elif role in ['node_onboard', 'node-onboard']:
                    add_msgs.append(f"Skipping non-PCD role '{role}'.")
                    continue
                else:
                    resp = pcd.put(url, {})
                if resp:
                    if resp.status_code == 200:
                        add_msgs.append(f"Role '{role}' applied successfully.")
                        changed = True
                    elif resp.status_code == 401:
                        self.fail_json(msg=f"Role '{role}' failed: unauthorized.")
                    elif resp.status_code == 500:
                        self.fail_json(msg=f"Role '{role}' failed: internal error.")
                    else:
                        self.fail_json(msg=f"Unexpected status code {resp.status_code} while applying role '{role}'.")
                #else:
                #    self.fail_json(
                #        msg=f"Role '{role}' received no response from API call. the response is.. Aborting.")
                else:
                    add_msgs.append(
                        f"Role '{role}' is already applied. No changes made")
                    changed = True
            result['changed'] = changed
            result['msg'] = " | ".join(add_msgs)
            result['new_config'] = json.dumps(roles) if changed else "No changes"
            self.exit_json(**result)
        elif params['state'] == 'absent':
            removal_msgs = []
            current_roles = set(current_sub_roles)
            for role in roles:
                if role in current_roles:
                    url = f"{mgmt_url}resmgr/v2/hosts/{host_id}/roles/{role}"
                    resp = pcd.delete(url)
                    if resp.status_code == 200:
                        changed = True
                        removal_msgs.append(f"Role '{role}' removed.")
                    elif resp.status_code == 404:
                        removal_msgs.append(f"Role '{role}' not found. Skipped.")
                    else:
                        removal_msgs.append(f"Error removing role '{role}', status: {resp.status_code}")
                else:
                    removal_msgs.append(f"Role '{role}' not present. Skipped.")
            result['changed'] = changed
            result['msg'] = " | ".join(removal_msgs)
            self.exit_json(**result)
        else:
            self.fail_json(msg=f"Invalid state '{params['state']}'", **result)

def main():
    module = PCDRolesConfigModule()
    module.run()


if __name__ == '__main__':
    main()