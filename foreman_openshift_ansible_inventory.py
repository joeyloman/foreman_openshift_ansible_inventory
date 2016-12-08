#!/usr/bin/env python
# vim: set fileencoding=utf-8 :
#
# Created by Joey Loman <joey@binbash.org>
#
# This script is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with it.  If not, see <http://www.gnu.org/licenses/>.
#
# This script is based on the foreman_ansible_inventory script
# by Guido Günther <agx@sigxcpu.org>
#
from __future__ import print_function

import argparse
import copy
import os
import re
import requests
from requests.auth import HTTPBasicAuth
import sys
from time import time

try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser


try:
    import json
except ImportError:
    import simplejson as json


class ForemanInventory(object):
    config_paths = [
        "/etc/ansible/foreman.ini",
        os.path.dirname(os.path.realpath(__file__)) + '/foreman.ini',
    ]

    def __init__(self):
        self.inventory = dict()  # A list of groups and the hosts in that group
        self.cache = dict()   # Details about hosts in the inventory
        self.params = dict()  # Params of each host

    def run(self):
        if not self._read_settings():
            return False
        self._get_inventory()
        self._print_data()
        return True

    def _read_settings(self):
        # Read settings and parse CLI arguments
        if not self.read_settings():
            return False
        self.parse_cli_args()
        return True

    def _get_inventory(self):
        if self.args.refresh_cache:
            self.update_cache()
        elif not self.is_cache_valid():
            self.update_cache()
        else:
            self.load_inventory_from_cache()
            self.load_params_from_cache()
            self.load_cache_from_cache()

    def _print_data(self):
        data_to_print = ""
        if self.args.host:
            data_to_print += self.get_host_info()
        else:
            self.inventory['_meta'] = {'hostvars': {}}
            for hostname in self.cache:
                # we only use the host parameters in satellite for the openshift installation
                self.inventory['_meta']['hostvars'][hostname] = self.params[hostname]

            data_to_print += self.json_format_dict(self.inventory, True)

        print(data_to_print)

    def is_cache_valid(self):
        """Determines if the cache is still valid"""
        if os.path.isfile(self.cache_path_cache):
            mod_time = os.path.getmtime(self.cache_path_cache)
            current_time = time()
            if (mod_time + self.cache_max_age) > current_time:
                if (os.path.isfile(self.cache_path_inventory) and
                    os.path.isfile(self.cache_path_params)):
                    return True
        return False

    def read_settings(self):
        """Reads the settings from the foreman.ini file"""

        config = ConfigParser.SafeConfigParser()
        env_value = os.environ.get('FOREMAN_INI_PATH')
        if env_value is not None:
            self.config_paths.append(os.path.expanduser(os.path.expandvars(env_value)))

        config.read(self.config_paths)

        # Foreman API related
        try:
            self.foreman_url = config.get('foreman', 'url')
            self.foreman_user = config.get('foreman', 'user')
            self.foreman_pw = config.get('foreman', 'password')
            self.foreman_ssl_verify = config.getboolean('foreman', 'ssl_verify')
        except (ConfigParser.NoOptionError, ConfigParser.NoSectionError) as e:
            print("Error parsing configuration: %s" % e, file=sys.stderr)
            return False

        # Cache related
        try:
            cache_path = os.path.expanduser(config.get('cache', 'path'))
        except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
            cache_path = '.'
        (script, ext) = os.path.splitext(os.path.basename(__file__))
        self.cache_path_cache = cache_path + "/%s.cache" % script
        self.cache_path_inventory = cache_path + "/%s.index" % script
        self.cache_path_params = cache_path + "/%s.params" % script
        try:
            self.cache_max_age = config.getint('cache', 'max_age')
        except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
            self.cache_max_age = 60
        return True

    def parse_cli_args(self):
        """Command line argument processing"""

        parser = argparse.ArgumentParser(description='Produce an Ansible Inventory file based on foreman')
        parser.add_argument('--list', action='store_true', default=True, help='List instances (default: True)')
        parser.add_argument('--host', action='store', help='Get all the variables about a specific instance')
        parser.add_argument('--refresh-cache', action='store_true', default=False,
                            help='Force refresh of cache by making API requests to foreman (default: False - use cache files)')
        self.args = parser.parse_args()

    def _get_json(self, url, ignore_errors=None):
        page = 1
        results = []
        while True:
            ret = requests.get(url,
                               auth=HTTPBasicAuth(self.foreman_user, self.foreman_pw),
                               verify=self.foreman_ssl_verify,
                               params={'page': page, 'per_page': 250})
            if ignore_errors and ret.status_code in ignore_errors:
                break
            ret.raise_for_status()
            json = ret.json()
            # /hosts/:id has not results key
            if 'results' not in json:
                return json
            # Facts are returned as dict in results not list
            if isinstance(json['results'], dict):
                return json['results']
            # List of all hosts is returned paginaged
            results = results + json['results']
            if len(results) >= json['total']:
                break
            page += 1
            if len(json['results']) == 0:
                print("Did not make any progress during loop. "
                      "expected %d got %d" % (json['total'], len(results)),
                      file=sys.stderr)
                break
        return results

    def _get_hosts(self):
        return self._get_json("%s/api/v2/hosts" % self.foreman_url)

    def _get_all_params_by_id(self, hid):
        url = "%s/api/v2/hosts/%s" % (self.foreman_url, hid)
        ret = self._get_json(url, [404])
        if ret == []:
            ret = {}
        ret = ret.get('all_parameters', {})
        for param in ret:
            if param["value"][0] == '[':
                param["value"] = json.loads(param["value"])
        return ret

    def _resolve_params(self, host):
        """Fetch host params and convert to dict"""
        params = {}

        for param in self._get_all_params_by_id(host['id']):
            name = param['name']
            params[name] = param['value']

        return params

    def update_cache(self):
        """Make calls to foreman and save the output in a cache"""
        self.hosts = dict()

        for host in self._get_hosts():
            dns_name = host['name']
            params = self._resolve_params(host)

            try:
                if params['openshift-role']:
                    roles = params['openshift-role'].split(',')
            except KeyError:
                roles = None

            if roles:
                for role in roles:
                    safe_key = self.to_safe(role)
                    self.push(self.inventory, safe_key, dns_name)

                self.cache[dns_name] = host
                self.params[dns_name] = params
                self._write_cache()

    def _write_cache(self):
        self.write_to_cache(self.cache, self.cache_path_cache)
        self.write_to_cache(self.inventory, self.cache_path_inventory)
        self.write_to_cache(self.params, self.cache_path_params)

    def get_host_info(self):
        """Get variables about a specific host"""

        if not self.cache or len(self.cache) == 0:
            # Need to load index from cache
            self.load_cache_from_cache()

        if self.args.host not in self.cache:
            # try updating the cache
            self.update_cache()

            if self.args.host not in self.cache:
                # host might not exist anymore
                return self.json_format_dict({}, True)

        return self.json_format_dict(self.cache[self.args.host], True)

    def push(self, d, k, v):
        if k in d:
            d[k].append(v)
        else:
            d[k] = [v]

    def load_inventory_from_cache(self):
        """Read the index from the cache file sets self.index"""

        cache = open(self.cache_path_inventory, 'r')
        json_inventory = cache.read()
        self.inventory = json.loads(json_inventory)

    def load_params_from_cache(self):
        """Read the index from the cache file sets self.index"""

        cache = open(self.cache_path_params, 'r')
        json_params = cache.read()
        self.params = json.loads(json_params)

    def load_cache_from_cache(self):
        """Read the cache from the cache file sets self.cache"""

        cache = open(self.cache_path_cache, 'r')
        json_cache = cache.read()
        self.cache = json.loads(json_cache)

    def write_to_cache(self, data, filename):
        """Write data in JSON format to a file"""
        json_data = self.json_format_dict(data, True)
        cache = open(filename, 'w')
        cache.write(json_data)
        cache.close()

    @staticmethod
    def to_safe(word):
        '''Converts 'bad' characters in a string to underscores

        so they can be used as Ansible groups

        >>> ForemanInventory.to_safe("foo-bar baz")
        'foo_barbaz'
        '''
        regex = "[^A-Za-z0-9\_]"
        return re.sub(regex, "_", word.replace(" ", ""))

    def json_format_dict(self, data, pretty=False):
        """Converts a dict to a JSON object and dumps it as a formatted string"""

        if pretty:
            return json.dumps(data, sort_keys=True, indent=2)
        else:
            return json.dumps(data)

if __name__ == '__main__':
    inv = ForemanInventory()
    sys.exit(not inv.run())
