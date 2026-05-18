import argparse
from modules import helper

# User input
parser = argparse.ArgumentParser()
parser.add_argument("--cloud",  help="cloud name from clouds.yaml")
parser.add_argument("--admin-cloud", help="cloud name for admin operations; required only when --image-file is used")
parser.add_argument("--name", help="base name for resources")
parser.add_argument("--image-file", help="local image path to upload to Glance")
parser.add_argument("--image-name", help="existing Glance image name to use for the VM (skips upload)")
parser.add_argument("--delete", action="store_true", help="delete resources instead of creating")
args = parser.parse_args()

if not args.delete:
    if not args.image_file and not args.image_name:
        parser.error("one of --image-file or --image-name is required for create operations")
    if args.image_file and not args.admin_cloud:
        parser.error("--admin-cloud is required when --image-file is provided (image upload requires admin endpoint)")

conn = helper.create_connection(args.cloud)
adminconn = helper.create_connection(args.admin_cloud) if args.admin_cloud else None

if args.delete:
    helper.delete_resources(conn, args.name)
    print("resources deleted successfully.")
else:
    net = helper.create_network(conn, f"{args.name}-network")
    subnet = helper.create_subnet(conn, f"{args.name}-subnet", net.id)
    if args.image_file:
        image = helper.upload_image(adminconn, f"{args.name}-image", args.image_file)
        image_ref = image.id
    else:
        image_ref = args.image_name
    volume = helper.create_volume(conn, f"{args.name}-volume", size=3)
    server = helper.create_instance(conn, args.name, flavor="m1.tiny", network_id=net.id, image_name=image_ref)
    print(f"Instance {server.name} created successfully.")

