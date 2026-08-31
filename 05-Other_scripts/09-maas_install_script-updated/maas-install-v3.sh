#!/bin/bash

MAAS_RELEASE="3.7.1"
MAAS_REPOSITORY="ppa:maas/3.7"

# accept arguments (order: DB_USER DB_NAME DB_PASSWORD MAAS_USER MAAS_PASSWORD MAAS_EMAIL)
if [ $# -ge 6 ]; then
    DB_USER="$1"
    DB_NAME="$2"
    DB_PASSWORD="$3"
    MAAS_USERNAME="$4"
    MAAS_PASSWORD="$5"
    MAAS_EMAIL="$6"
fi

# check for packages and install if not present
check_packages() {
    # Check if required packages are installed
    sudo apt-get update
    for package in "$@"; do
        if ! dpkg -l | grep -q "^ii  $package "; then
            echo "Package $package is not installed. Installing..."
            sudo apt install -y "$package"
        else
            echo "Package $package is already installed."
        fi
    done
}

# check network connectivity and select the best interface with default gateway based on metric
check_network_connectivity() {
    # Get all default gateway interfaces with their metrics
    INTERFACES=($(ip -4 route show default | awk '{print $5, $NF}' | sort -k2n | awk '{print $1}'))
    if [[ ${#INTERFACES[@]} -eq 0 ]]; then
        echo "No default gateway interfaces found."
        return 1  # False
    fi
    echo "Available default gateway interfaces: ${INTERFACES[*]}"

    # Pick the interface with the lowest metric
    CHOSEN_IFACE=${INTERFACES[0]}
    if [[ ${#INTERFACES[@]} -gt 1 ]]; then
        echo "Multiple default gateway interfaces found. Testing connectivity..."

        for IFACE in "${INTERFACES[@]}"; do
            echo "Testing connectivity via $IFACE..."
            if ping -I "$IFACE" -c 3 -W 2 8.8.8.8 &>/dev/null; then
                echo "Selected interface: $IFACE (successful ping)"
                CHOSEN_IFACE=$IFACE
                break
            fi
        done
    fi
    echo "selected interface: $CHOSEN_IFACE"

    # Validate internet connectivity
    if ! ping -I "$CHOSEN_IFACE" -c 3 -W 2 8.8.8.8 &>/dev/null; then
        echo "Internet connectivity test failed: Cannot reach 8.8.8.8 via $CHOSEN_IFACE."
        return 1  # False
    fi

    # Validate DNS resolution
    if ! nslookup google.com &>/dev/null; then
        echo "DNS resolution test failed: Cannot resolve google.com."
        return 1  # False
    fi

    echo "All network checks passed using interface: $CHOSEN_IFACE"
    return 0  # True
}

install_maas() {
    echo

    if [ "$(. /etc/os-release && printf '%s' "$VERSION_ID")" != "24.04" ]; then
        echo "MAAS $MAAS_RELEASE requires Ubuntu 24.04 LTS."
        return 1
    fi

    sudo apt update
    sudo systemctl disable --now systemd-timesyncd
    echo "Disabling systemd-timesyncd... to avoid conflicts with chrony services"
    sudo apt-get remove systemd-timesyncd -y

    # Check if PostgreSQL is installed
    if dpkg -l | grep -q "^ii  postgresql "; then
        echo "PostgreSQL is already installed. Skipping database user and creation steps."
    else
        check_packages "postgresql"

        # create DB user and DB
        sudo -i -u postgres psql -c "CREATE USER \"$DB_USER\" WITH ENCRYPTED PASSWORD '$DB_PASSWORD'"
        sudo -i -u postgres createdb -O "$DB_USER" "$DB_NAME"
    fi

    sudo apt-add-repository "$MAAS_REPOSITORY" -y
    sudo apt update

    # Select the exact 3.7.1 build published for the current Ubuntu release.
    MAAS_PACKAGE_VERSION=$(apt-cache madison maas | awk -v release="$MAAS_RELEASE" '$3 ~ ("^[0-9]+:" release "([.+~-]|$)") {print $3; exit}')
    if [ -z "$MAAS_PACKAGE_VERSION" ]; then
        echo "MAAS $MAAS_RELEASE is not available from $MAAS_REPOSITORY for this system."
        return 1
    fi
    sudo apt-get -y install "maas=$MAAS_PACKAGE_VERSION"

    PG_HBA_FILE="/etc/postgresql/16/main/pg_hba.conf"
    if [ ! -f "$PG_HBA_FILE" ]; then
        echo "PostgreSQL 16 authentication file was not found at $PG_HBA_FILE."
        return 1
    fi
    if ! sudo grep -Fqx "host    $DB_NAME    $DB_USER    0/0    md5" "$PG_HBA_FILE"; then
        echo "host    $DB_NAME    $DB_USER    0/0    md5" | sudo tee -a "$PG_HBA_FILE" > /dev/null
        sudo systemctl reload postgresql
    fi

    sudo maas createadmin --username "$MAAS_USERNAME" --password "$MAAS_PASSWORD" --email "$MAAS_EMAIL"

    if ! maas --version | grep -q "$MAAS_RELEASE"; then
        echo "MAAS installation completed, but the installed version is not $MAAS_RELEASE."
        return 1
    fi
    echo "MAAS $MAAS_RELEASE installation and configuration complete."
}

# main script execution
echo "Starting MAAS installation script..."
echo " "
echo "Checking network connectivity..."
if check_network_connectivity; then
    echo "Network is reachable."
    echo " "
    echo "Checking and installing additional required packages..."
    check_packages "tree" "net-tools" "ansible" "python3-openstackclient"
    echo " "

    # only prompt if not provided via args or env
    [ -z "$MAAS_USERNAME" ] && read -p "Enter MAAS username: " MAAS_USERNAME
    if [ -z "$MAAS_PASSWORD" ]; then
        read -s -p "Enter MAAS password: " MAAS_PASSWORD
        echo
    fi
    [ -z "$MAAS_EMAIL" ] && read -p "Enter MAAS email: " MAAS_EMAIL
    [ -z "$DB_NAME" ] && read -p "Enter PostgreSQL database name: " DB_NAME
    [ -z "$DB_USER" ] && read -p "Enter PostgreSQL username: " DB_USER
    if [ -z "$DB_PASSWORD" ]; then
        read -s -p "Enter PostgreSQL password: " DB_PASSWORD
        echo
    fi

    echo
    echo "Proceeding with MAAS installation..."
    install_maas
else
    echo "Network check failed."
    echo "Please check your network configuration and try again."
fi
