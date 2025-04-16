from openstack import connection
import time

def create_connection(cloud_name):
    return connection.from_config(cloud=cloud_name)

# image wait
def wait_for_status(conn, resource, desired_status='active', timeout=300, interval=5):
    return conn.image.wait_for_status(
        resource,
        status=desired_status,
        failures=['error'],
        interval=interval,
        wait=timeout
    )

#cinder wait
def wait_for_volume_status(conn, resource, desired_status='available', timeout=300, interval=5):
    return conn.block_storage.wait_for_status(
        resource,
        status=desired_status,
        failures=['error'],
        interval=interval,
        wait=timeout
    )

def create_network(conn, name):
    print(f"Creating network: {name}")
    return conn.network.create_network(name=name, is_router_external=False)

def create_subnet(conn, name, network_id):
    print(f"Creating subnet: {name}")
    return conn.network.create_subnet(
        name=name,
        network_id=network_id,
        ip_version=4,
        cidr='192.168.100.0/24'
    )
def upload_image(conn, image_name, image_file):
    print(f"Uploading image: {image_name}")
    image = conn.image.upload_image(
        name=image_name,
        data=open(image_file, 'rb'),
        disk_format='qcow2',
        container_format='bare',
        visibility='private'
    )
    return wait_for_status(conn, resource=image)


def create_volume(conn, name, size):
    print(f"Creating volume: {name}")
    volume = conn.block_storage.create_volume(name=name, size=size)
    return wait_for_volume_status(conn, resource=volume)

def create_instance(conn, name, flavor, network_id, image_name):
    print(f"Creating server: {name}")

    flavor_obj = conn.compute.find_flavor(flavor)
    if not flavor_obj:
        raise Exception(f"Flavor '{flavor}' not found")

    image_obj = conn.compute.find_image(image_name)
    if not image_obj:
        raise Exception(f"Image '{image_name}' not found")

    server_data = {
        "name": name,
        "flavor_id": flavor_obj.id,
        "image_id": image_obj.id,
        "networks": [{"uuid": network_id}]
    }

    server = conn.compute.create_server(**server_data)
    server = conn.compute.wait_for_server(server, wait=300)
    return server

def delete_resources(conn, base_name):
    print("Deleting resources...")
    for server in conn.compute.servers(name=base_name):
        print(f"Deleting server: {server.name}")
        conn.compute.delete_server(server, ignore_missing=True)
        time.sleep(20)
    for volume in conn.block_storage.volumes(name=f"{base_name}-volume"):
        print(f"Deleting volume: {volume.name}")
        conn.block_storage.delete_volume(volume, ignore_missing=True)

    for subnet in conn.network.subnets(name=f"{base_name}-subnet"):
        print(f"Deleting subnet: {subnet.name}")
        conn.network.delete_subnet(subnet, ignore_missing=True)

    for net in conn.network.networks(name=f"{base_name}-network"):
        print(f"Deleting network: {net.name}")
        conn.network.delete_network(net, ignore_missing=True)

    for image in conn.image.images(name=f"{base_name}-image"):
        print(f"Deleting image: {image.name}")
        conn.image.delete_image(image, ignore_missing=True)
