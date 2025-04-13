### Howto Use this script?

#### 02-deploy-instance_E2E
This sample can do following things:
- Deploy nova instance based on user provided counts
- Deploy independent cinder volume and attach to the instance
- Deploy networks and subnet and attach to instance
- Deploy independent images to glance based on user inputs. 
- The cinder and image can be individually  excluded/included with apply command.

Steps to execute:
- Ensure `opentofu` packages are installed on the host and the host has access to the PCD environment. 
- Download the required directory locally host.
- From inside the directory, run:
```bash
tofu init
```
- Configure the `testdeploy.tfvars` file to have the necessary openstack auth configuration along with image and  glance config:
```bash
openstack_user_name = <usernmame>
openstack_tenant_name = "service"
openstack_password = <password>
openstack_auth_url = "https://<URL>/keystone/v3"
image_name = "<actual name of the image present in the glance>"
flavor_name = "m1.medium"
glance_image_name = "<name of the image that is to be uploaded to glance>"
```
- Copy the required glance image inside this directory.
- Set the required number of resources for each type in `vars.yaml` under:
```bash
variable "resourcecount" {
  type = map(number)
  default = {
    net  = 3
    vol  = 5
    inst = 3
    imgs = 5
  }
}
NOTE: the net and insts count should be equal.
```
- Run plan and apply command with tofu. To include volume and image deployment:
```bash
tofu  plan  -var-file testdeploy.tfvars -var="deploy_image=true" -var="deploy_volume=true"
tofu  apply  -var-file testdeploy.tfvars -var="deploy_image=true" -var="deploy_volume=true" 
```
Type `yes` for the apply action. 
- To deploy without image or volume creation test:
```bash
tofu  plan  -var-file testdeploy.tfvars 
tofu  apply  -var-file testdeploy.tfvars 
```