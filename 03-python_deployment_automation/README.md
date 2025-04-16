### Howto Use this script?

#### 03-python_deployment_automation/
This sample can do following things:
- Deploy independent images to glance
- Deploy networks and subnet as a fresh
- Deploy single nova instance with boot from image option


Steps to execute:
- Install openstack sdk library: `pip3 install  openstacksdk` (if not installed)
- Update the openstacksdk packages: `pip3 install --upgrade openstacksdk`
- Configure the local `clouds.yaml` file with the required credentials of the cloud. Ensure there is one profile for admin and one for public interface:
```bash
cat /home/ubuntu/.config/openstack/clouds.yaml
clouds:
  sa-demo_public:
    auth:
      auth_url: https://<DU-URL>/keystone/v3
      username: ""
      password: ""
      project_name: "service"
      user_domain_name: "Default"
      project_domain_name: "Default"
    region_name: "region2"
    identity_api_version: 3
    interface: "public"
    verify: false
  sa-demo_admin:
    auth:
      auth_url: https://<DU-URL>/keystone/v3
      username: ""
      password: ""
      project_name: "service"
      user_domain_name: "Default"
      project_domain_name: "Default"
    region_name: "region2"
    identity_api_version: 3
    interface: admin
    verify: false
```
- From inside this example directory trigger the deployment action with:
```bash
python3 create_delete_instance.py --cloud sa-demo_public --name testVMPy1 --image-file cirros-0.6.3-x86_64-disk.img
```
- To remove all the resources after test RUn the delete resource playbook:
```bash
 python3 create_delete_instance.py --cloud sa-demo_public --name testVMPy1 --delete
```
