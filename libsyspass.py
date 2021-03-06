#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

# python 3 headers, required if submitting to Ansible
from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = """
      DISCLAIMER: This module has been heavily inspired by https://github.com/ansible/ansible/blob/devel/lib/ansible/plugins/lookup/password.py for password generation and term handling and thus is under GPL.

      lookup: syspass
        author: Gousseaud Gaëtan <gousseaud.gaetan.pro@gmail.com>, Pierre-Henry Muller <pierre-henry.muller@digdeo.fr>
        short_description: get syspass user password and syspass API client
        description:
            - This lookup returns the contents from Syspass database, a user's password more specificly. Other functions are also implemented for further use.
        ansible_version: ansible > 2.6 with or without mitogen
        python_version: 2.7.9
        syspass_version: > 3.0
        params:
           -term: the account name (required and must be unique)
             -login: login given to created account
             -category: category given to created account
             -customer: client given to created account
             -state: like in Ansible absent to remove the password, present in default to create (Optional)
             -pass_length: generated password length (Optional)
             -chars: type of chars used in generated (Optional)
             -url: url given to created account (Optional)
             -notes: notes given to created account (Optional)
             -private: is this password private for users who have access or public for all users in acl (default false)
             -privategroup: is private only for users in same group (default false)
             -expirationDate: expiration date given to created account (Optional) and not tested (no entry in webui)

        notes:
          - Account is only created if exact name has no match.
          - A different field passed to an already existing account wont modify it.
          - Utility of tokenPass: https://github.com/nuxsmin/sysPass/issues/994#issuecomment-409050974
          - Rudimentary list of API accesses (Deprecated): https://github.com/nuxsmin/sysPass/blob/d0056d74a8a2845fb3841b02f4af5eac3e4975ed/lib/SP/Services/Api/ApiService.php#L175
          - Usage of ansible vars: https://github.com/ansible/ansible/issues/33738#issuecomment-350819222

        syspass function list:
          SyspassClient:
            Account:
              -AccountSearch
              -AccountViewpass
              -AccountCreate
              -AccountDelete
              -AccountView
            Category:
              -CategorySearch
              -CategoryCreate
              -CategoryDelete
            Client:
              -ClientSearch
              -ClientCreate
              -ClientDelete
            Tag:
              -TagCreate
              -TagSearch
              -TagDelete
            UserGroup:
              - UserGroupCreate
              - UserGroupSearch
              - UserGroupDelete
            Others:
              -Backup
"""

EXAMPLES = """
### IN HOST VARS ###

syspass_API_URL: http://syspass-server.net/api.php
syspass_API_KEY: 'API_KEY' #Found in Users & Accesses -> API AUTHORIZATION -> User token
syspass_API_ACC_TOKPWD: Password for API_KEY for Account create / view / delete password account permission in API
syspass_default_length: number of chars in password

### IN PLAYBOOK ###

NOTE: Default values are handled 

##### USAGE 1 #####

- name: Minimum declaration to get / create password
  local_action: debug msg="{{ lookup('syspass', 'Server 1 test account', login=test, category='MySQL', customer='Customer 1') }}"

- name: All details for password declaration
  local_action: debug msg="{{ lookup('syspass', 'Server 1 test account', login=test, category='MySQL', customer='Customer 1', 
    url='https://exemp.le', notes='Additionnal infos', private=True, privategroupe=True) }}"

- name: Minimum declaration to delete password
  local_action: debug msg="{{ lookup('syspass', 'Server 1 test account', state=absent) }}"


"""

import json
import requests
import random
import string
import urllib3
import re
import sys
from ansible.errors import AnsibleError, AnsibleAssertionError
from ansible.module_utils._text import to_native, to_text
from ansible.plugins.lookup import LookupBase
from ansible.utils.encrypt import do_encrypt, random_password

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()
    
class SyspassClient:
    def __init__(self, API_KEY, API_URL, API_ACC_TOKPWD):
        self.API_KEY = API_KEY
        self.API_URL = API_URL
        self.API_ACC_TOKPWD = API_ACC_TOKPWD
        self.rId = 1

    def AccountSearch(self, text, count = None, categoryId = None, clientId = None, matchAll = None):
        """
        Search account in syspass using text as keyword,
        can apply categoryId of clientId as a filter.
        """
        data = {   "jsonrpc": "2.0",
                   "method": "account/search",
                   "params": {
                       "authToken": self.API_KEY,
		       "text": text,
                       "count": count,
                       "categoryId": categoryId,
                       "clientId": clientId},
                   "id": self.rId }

        self.rId+=1
        req = requests.post(self.API_URL, json = data)
        req = req.json()
        if req['result']['count'] > 0:
            if matchAll == None:
                for res in req['result']['result']:
                    if res['name'] == text:
                        return req['result']['result'][0]
            else:
                return req['result']['result']
        elif 'error' in req:
            raise AnsibleError('AccountSearch Error : %s' % (req))
        else:
            return None

    def AccountViewpass(self, uId):
        """
        Returns account's password. 
        uId identifies account.
        tokenPass is used to decrypt encrypted data.
        """
        data = {"jsonrpc": "2.0",
                "method": "account/viewPass",
                "params":{
                    "authToken": self.API_KEY,
                    "id": uId,
                    "tokenPass": self.API_ACC_TOKPWD
                },
                "id": self.rId 
        }

        self.rId+=1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['count'] > 0:
            return req['result']['result']['password']
        else:
            raise AnsibleError('AccountViewpass Error : %s' % (req))
    
    def AccountCreate(self,
                      name,
                      categoryId,
                      clientId,
                      password,
                      login,
                      url = None,
                      tags = [],
                      notes = None,
                      private = None,
                      privateGroup = None,
                      userGroupId = None,
                      expireDate = None,
                      parentId = None):
        """
        Creates account for syspass.
        """
        data = {"jsonrpc": "2.0",
                "method": "account/create",
                "params":{
                    "authToken": self.API_KEY,
                    "tokenPass": self.API_ACC_TOKPWD,
                    "name": name,
                    "categoryId": categoryId,
                    "clientId": clientId,
                    "userGroupId": userGroupId,
                    "pass": password,
                    "login": login,
                    "url": url,
                    "tagsId": tags,
                    "notes": notes,
                    "private": private,
                    "privateGroup": privateGroup,
                    "expireDate": expireDate,
                    "parentId": parentId
		},
		"id": self.rId
        }
        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['itemId'] > 0:
            return req['result']
        else:
            raise AnsibleError('AccountCreate Error : %s' % (req))

    def AccountDelete(self, uId):
        """
        Delete syspass account.
        """
        data = {"jsonrpc": "2.0",
                "method": "account/delete",
		"params":{
	            "authToken": self.API_KEY,
                    "id": uId,
                    "tokenPass": self.API_ACC_TOKPWD
                },
                "id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['resultCode'] == 0:
            return req['result']
        else:
            raise AnsibleError('AccountDelete Error : %s' % (req))

    def AccountView(self, uId):
        """
        View syspass account.
        """
        data = {"jsonrpc": "2.0",
                "method": "account/view",
                "params":{
                    "authToken": self.API_KEY,
                    "id": uId
                },
                "id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['count'] > 0:
            return req['result']['result']
        else:
            raise AnsibleError('AccountView Error : %s' % (req))
        
    
    def CategorySearch(self,text, count = None):
        """
        Searches syspass category.
        text is the keyword.
        count is the number of results.
        """

        data = {"jsonrpc": "2.0",
                "method": "category/search",
                "params":{
                    "authToken": self.API_KEY,
                    "text": text,
                    "count": count
		},
		"id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['count'] > 0:
            for res in req['result']['result']:
                if res['name'] == text:
                    return req['result']['result'][0]
        elif 'error' in req:
            raise AnsibleError('CategorySearch Error : %s' % (req['error']))        
        else:
            return None
        
    def CategoryCreate(self, name, description = None):
        """
        Creates syspass category.
        """
        data = {"jsonrpc": "2.0",
                "method": "category/create",
                "params":{
                    "authToken": self.API_KEY,
                    "name": name,
                    "description": description
		},
                "id": self.rId
	}

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['itemId'] > 0:
            return req['result']
        else:
            raise AnsibleError('CategoryCreate Error : %s' % (req))

    def CategoryDelete(self, Id):
        """
        Deletes syspass category.
        """
        data = {"jsonrpc": "2.0",
                "method": "category/delete",
                "params":{
                    "authToken": self.API_KEY,
                    "id": Id
		},
                "id": self.rId
	}

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['resultCode'] == 0:
            return req['result']
        else:
            raise AnsibleError('CategoryDelete Error : %s' % (req))
        
    def ClientSearch(self, text, count = None):
        """
        Searches syspass client.
        """
        data = {"jsonrpc": "2.0",
                "method": "client/search",
                "params":{
                    "authToken": self.API_KEY,
                    "text": text,
                    "count": count
		},
		"id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['count'] > 0:
            for res in req['result']['result']:
                if res['name'].upper() == text.upper():
                    return req['result']['result'][0]
        elif 'error' in req:
            raise AnsibleError('ClientSearch Error : %s' % (req['error']))
        else:
            return None

    def ClientCreate(self, name, description = None, Global = False):
        """
        Creates a syspass client.
        """
        data = {"jsonrpc": "2.0",
                "method": "client/create",
                "params":{
                    "authToken": self.API_KEY,
                    "name": name,
                    "description": description,
                    "global": Global
		},
		"id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['itemId'] > 0:
            return req['result']
        else:
            raise AnsibleError('ClientCreate Error : %s' % (req))

    def ClientDelete(self, cId):
        """
        Deletes a syspass client.
        """
        data = {"jsonrpc": "2.0",
                "method": "client/delete",
                "params":{
                    "authToken": self.API_KEY,
                    "id": cId
		},
		"id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['resultCode'] == 0:
            return req['result']
        else:
            raise AnsibleError('ClientDelete Error : %s' % (req))

    def TagCreate(self,name):
        """
        Creates a syspass tag.
        """
        data = {"jsonrpc": "2.0",
                "method": "tag/create",
                "params":{
                    "authToken": self.API_KEY,
                    "name": name
                },
                "id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['itemId'] > 0:
            return req['result']
        else:
            raise AnsibleError('TagCreate Error : %s' % (req))
    
    def TagSearch(self, text, count = None):
        """
        Searches a syspass tag using text as keyword.
        """
        data = {"jsonrpc": "2.0",
                "method": "tag/search",
                "params":{
                    "authToken": self.API_KEY,
                    "text": text,
                    "count": count
		},
		"id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['count'] > 0:
            for res in req['result']['result']:
                if res['name'].upper() == text.upper():
                    return req['result']['result'][0]
        elif 'error' in req:
            raise AnsibleError('TagSearch Error : %s' % (req['error']))
        else:
            return None
        
    def TagDelete(self,tId):
        """
        Deletes syspass tag using id.
        """
        data = {"jsonrpc": "2.0",
                "method": "tag/delete",
                "params":{
                    "authToken": self.API_KEY,
                    "id" : tId
                },
                "id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['resultCode'] == 0:
            return req['result']
        else:
            raise AnsibleError('TagDelete Error : %s' % (req))

    def UserGroupCreate(self,name,description):
        """
        Creates a syspass User Group.
        """
        data = {"jsonrpc": "2.0",
                "method": "userGroup/create",
                "params":{
                    "authToken": self.API_KEY,
                    "name": name,
                    "description": description
                },
                "id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['itemId'] > 0:
            return req['result']
        else:
            raise AnsibleError('UserGroupCreate Error : %s' % (req))
    
    def UserGroupSearch(self, text, count = None):
        """
        Searches a syspass User Group using text as keyword.
        """
        data = {"jsonrpc": "2.0",
                "method": "userGroup/search",
                "params":{
                    "authToken": self.API_KEY,
                    "text": text,
                    "count": count
		},
		"id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['count'] > 0:
            for res in req['result']['result']:
                if res['name'].upper() == text.upper():
                    return req['result']['result'][0]
        elif 'error' in req:
            raise AnsibleError('UserGroupSearch Error : %s' % (req['error']))
        else:
            return None

    def UserGroupDelete(self,ugId):
        """
        Deletes syspass User Group using id.
        """
        data = {"jsonrpc": "2.0",
                "method": "userGroup/delete",
                "params":{
                    "authToken": self.API_KEY,
                    "id" : ugId
                },
                "id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        req = req.json()
        if req['result']['resultCode'] == 0:
            return req['result']
        else:
            raise AnsibleError('UserGroupDelete Error : %s' % (req))
    
    def Backup(self):
        """
        https://github.com/nuxsmin/sysPass/issues/1004#issuecomment-411487284
        """
        data = {"jsonrpc": "2.0",
                "method": "backup",
                "params":{
                    "authToken": self.API_KEY,
                },
                "id": self.rId
        }

        self.rId += 1
        req = requests.post(self.API_URL, json = data, verify = False)
        if 'result' in req.json():        
            return req.json()['result']
        else:
            raise AnsibleError('Backup Error : %s' % (req.json()))
