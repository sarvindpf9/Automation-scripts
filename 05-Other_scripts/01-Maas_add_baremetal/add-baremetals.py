import argparse
from modules import maasHelper


parser = argparse.ArgumentParser(description="Deploy MAAS machines with cloud-init")
parser.add_argument("--maas-user", required=True, help="MAAS username")
parser.add_argument("--csv-file", required=True, help="Path to CSV file")
args = parser.parse_args()
logger = maasHelper.setup_logger()
logger.info("Starting deployment of baremetal nodes...")
maasHelper.add_machines_from_csv(args.maas_user, args.csv_file)

