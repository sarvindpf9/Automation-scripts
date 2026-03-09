import os
from openstack import connection


def get_migrated_flavors(conn):
    """Get public flavors starting with 'MigratedVM-' excluding those with 'gpu'."""
    flavors = conn.compute.flavors(is_public=True)
    filtered = [
        f for f in flavors
        if f.name and f.name.startswith('MigratedVM-') and 'gpu' not in f.name.lower()
    ]
    return filtered


def delete_flavors(conn, flavors):
    """Delete list of flavors after confirmation."""
    if not flavors:
        print("No flavors to delete.")
        return

    print(f"\nFound {len(flavors)} flavors to delete:")
    for f in flavors:
        print(f"  - {f.name} ({f.id})")

    confirm = input("\nDelete these flavors? (yes/no): ").strip().lower()
    if confirm == 'yes':
        deleted_count = 0
        for f in flavors:
            try:
                conn.compute.delete_flavor(f.id)
                print(f"Deleted: {f.name} ({f.id})")
                deleted_count += 1
            except Exception as e:
                print(f"Failed to delete {f.name}: {e}")
        print(f"\nDeleted {deleted_count}/{len(flavors)} flavors.")
    else:
        print("Deletion cancelled.")


# Read from environment (set by sourcing RC file)
auth_url = os.environ.get('OS_AUTH_URL')
username = os.environ.get('OS_USERNAME')
password = os.environ.get('OS_PASSWORD')
project_name = os.environ.get('OS_PROJECT_NAME')
project_domain_name = os.environ.get('OS_PROJECT_DOMAIN_NAME', 'Default')
user_domain_name = os.environ.get('OS_USER_DOMAIN_NAME', 'Default')
identity_api_version = os.environ.get('OS_IDENTITY_API_VERSION', '3')

if not all([auth_url, username, password, project_name]):
    raise ValueError(
        "Missing required env vars: Source RC file and check OS_AUTH_URL, OS_USERNAME, OS_PASSWORD, OS_PROJECT_NAME")

# Create connection explicitly
conn = connection.Connection(
    auth_url=auth_url,
    username=username,
    password=password,
    project_name=project_name,
    project_domain_name=project_domain_name,
    user_domain_name=user_domain_name,
    identity_api_version=identity_api_version
)

# List with names
flavors = get_migrated_flavors(conn)
if flavors:
    print("\nFlavors found:")
    print(f"{'Name':<50} | UUID")
    print("-" * 70)
    for f in flavors:
        print(f"{f.name:<50} | {f.id}")
else:
    print("No matching flavors found.")

# Uncomment next line to enable deletion (admin required)
print("proceeding to delete the flavors...")
# delete_flavors(conn, flavors)
