#!/usr/bin/python

import json
import requests
from .logger import PCDLogger

class PCDConn:

    def __init__(self, mgmt_url, token):
        self.mgmt_url = mgmt_url
        self.token = token
        self.headers = {
                'X-Auth-Token': self.token,
                'Content-Type': 'application/json'
        }

    def make_request(self, method, url, body=None):
        if body:
            body = json.dumps(body)
        try:
            logger = PCDLogger('PCDConn')
            logger.debug(f"Request: {method} {url} {body}")
            response = requests.request(method, url, data=body, headers=self.headers)
            logger.debug(f"Response: {response.status_code} {response.text}")
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as http_err:
            if response.status_code == 404:
                return response
        except Exception as e:
            logger.error(f"Failed to make request: {e}")
            return None

    def delete(self, url):
        return self.make_request('DELETE', url)

    def get(self, url):
        return self.make_request('GET', url)

    def put(self, url, body):
        return self.make_request('PUT', url, body)

    def post(self, url, body):
        return self.make_request('POST', url, body)
