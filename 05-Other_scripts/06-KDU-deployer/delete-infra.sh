#!/bin/bash

# FIRST, EDIT "deploy.env"
# this script deploys ONLY the "Infra" region

source deploy.env
export CUSTOMER=$1

if [ "$CUSTOMER" == "" ]; then
    echo "ERROR: customer name required"
    echo "usage: $0: <customername>"
    exit
fi

curl https://$BORK/api/v1/customers/$CUSTOMER -X DELETE --data-binary "{\"admin_email\":\"$EMAIL\"}"
curl https://$BORK/api/v1/regions/$CUSTOMER.$DOMAIN -X DELETE --data-binary "{\"customer\":\"$CUSTOMER\"}"
curl https://$BORK/api/v1/regions/$CUSTOMER.$DOMAIN -X DELETE 
curl https://$BORK/api/v1/regions/$CUSTOMER.$DOMAIN -X BURN 


