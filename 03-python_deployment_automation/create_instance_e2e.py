import argparse
from modules import helper

# User input
parser = argparse.ArgumentParser()
parser.add_argument("--cloud",  help="cloud name from clouds.yaml")
parser.add_argument("--name", help="base name for resources")
parser.add_argument("--image-file", help="local image path")
parser.add_argument("--delete", action="store_true", help="delete resources instead of creating")
args = parser.parse_args()

conn = helper.create_connection(args.cloud)
adminconn = helper.create_connection("sa-demo_admin")

if args.delete:
    helper.delete_resources(conn, args.name)
    print("resources deleted successfully.")
else:
    net = helper.create_network(conn, f"{args.name}-network")
    subnet = helper.create_subnet(conn, f"{args.name}-subnet", net.id)
    image = helper.upload_image(adminconn, f"{args.name}-image", args.image_file)
    volume = helper.create_volume(conn, f"{args.name}-volume", size=3)
    server = helper.create_instance(conn, args.name, flavor="m1.tiny", network_id=net.id, image_name=image.id)
    print(f"Instance {server.name} created successfully.")

