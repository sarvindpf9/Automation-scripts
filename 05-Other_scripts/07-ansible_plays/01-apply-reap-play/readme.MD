# Apply PCD host tuning 

This directory contains an Ansible playbook to apply the following changes on the pcd cluster hosts:
- `aio-max-nr` tuning for increasing the default AIO context limits
- Set `running_deleted_instance_action` nova ovrride options to `reap`.

## Files
- `02-nova-store-tune.yml`: Main Ansible playbook.
- `inventory`: Hosts and groups definitions.
- `apply_reap_libvirt.sh`: Script to apply the libvirt tuning

## Prerequisites
- Ansible 2.9+
- Access to target hosts (SSH or API)
- Properly configured inventory and variables

## Usage
1. Clone this repository or copy the directory.
2. Create an inventory file inside the same directory. example of an inventory file:
```
snn:
  vars:
    pcd:
      region: snn
  children:
    stage:
      vars:
        environment: stage
      hosts:
        snnhv0004.ies.mentorg.com:
          ansible_ssh_user: "gvs"
          ansible_ssh_private_key_file: "/home/gvs/.ssh/id_rsa"
```

3. The playbook has two boolean which can help to apply either one of the fix at a time or can be applied together:
   1. 
   ```bash
   ansible-playbook -i inventory playbook.yml
   ```
4. Review output and logs for results.

## Customization
- Modify roles in `roles/` to add or change resource management logic.
- Adjust variables in `vars/` for different environments or requirements.

## Support
For issues or questions, please contact the repository maintainer or open an issue.
