#!/bin/bash

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

      # Decide MAAS repo based on lsb-release
      LSB_FILE="/etc/lsb_release"
      [ -f /etc/lsb-release ] && LSB_FILE="/etc/lsb-release"
      REPO="ppa:maas/3.5"
      if [ -f "$LSB_FILE" ] && grep -qi "ubuntu" "$LSB_FILE" && grep -qE "DISTRIB_RELEASE=24(\.|$)|24(\.|$)" "$LSB_FILE"; then
        REPO="ppa:maas/3.6"
      fi

      sudo apt-add-repository "$REPO" -y
      sudo apt update
      sudo apt-get -y install maas

      echo "host    $DB_NAME    $DB_USER    0/0    md5" | sudo tee -a /etc/postgresql/14/main/pg_hba.conf > /dev/null
      sudo maas createadmin --username "$MAAS_USERNAME" --password "$MAAS_PASSWORD" --email "$MAAS_EMAIL"
      echo "MAAS installation and configuration complete."
    fi
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
