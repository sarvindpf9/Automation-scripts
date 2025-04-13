## Sample terraform scripts for testing Workload deployments

This repo contains some viable terraform templates that can be used to quickly spin up various sets of resources in PCD environment which can be used for validation and testing the integrity of the customer or test setup. 

Each directory is a independent template which can be individually downloaded and executed as per needs. 

### Howto 

#### 01-deploy_bulk-workload
This sample can do following things:
- Deploy nova instances based on user provided counts. The instances are mapped to the subnets that will be created.
- Deploy independent cinder volumes based on user provided counts
- Deploy networks and subnet in bulk
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