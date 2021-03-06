#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2017, F5 Networks Inc.
# GNU General Public License v3.0 (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = r'''
---
module: bigip_security_address_list
short_description: Manage address lists on BIG-IP AFM
description:
  - Manages the AFM address lists on a BIG-IP. This module can be used to add
    and remove address list entries.
version_added: "2.5"
options:
  name:
    description:
      - Specifies the name of the address list.
    required: True
  partition:
    description:
      - Device partition to manage resources on.
    default: Common
    version_added: 2.5
  description:
    description:
      - Description of the address list
  geo_locations:
    description:
      - List of geolocations specified by their C(country) and C(region).
    suboptions:
      type:
        country:
          - The country name, or code, of the geolocation to use.
          - In addition to the country full names, you may also specify their abbreviated
            form, such as C(US) instead of C(United States).
          - Valid country codes can be found here https://countrycode.org/.
        required: true
        choices:
          - Any valid 2 character ISO country code.
          - Any valid country name.
      region:
        description:
          - Region name of the country to use.
        choices:
  address_ranges:
    description:
      - A list of address ranges where the range starts with a port number, is followed
        by a dash (-) and then a second number.
      - If the first address is greater than the second number, the numbers will be
        reversed so-as to be properly formatted. ie, C(2.2.2.2-1.1.1). would become
        C(1.1.1.1-2.2.2.2).
  address_lists:
    description:
      - Simple list of existing address lists to add to this list. Address lists can be
        specified in either their fully qualified name (/Common/foo) or their short
        name (foo). If a short name is used, the C(partition) argument will automatically
        be prepended to the short name.
  fqdns:
    description:
      - A list of fully qualified domain names (FQDNs).
      - An FQDN has at least one decimal point in it, separating the host from the domain.
      - To add FQDNs to a list requires that a global FQDN resolver be configured.
        At the moment, this must either be done via C(bigip_command), or, in the GUI
        of BIG-IP. If using C(bigip_command), this can be done with C(tmsh modify security
        firewall global-fqdn-policy FOO) where C(FOO) is a DNS resolver configured
        at C(tmsh create net dns-resolver FOO).
  state:
    description:
      - When C(present), ensures that the address list and entries exists.
      - When C(absent), ensures the address list is removed.
    default: present
    choices:
      - present
      - absent
    version_added: 2.5
extends_documentation_fragment: f5
author:
  - Tim Rupp (@caphrim007)
'''

EXAMPLES = r'''
- name: Create an address list
  bigip_security_address_list:
    name: foo
    addresses:
      - 3.3.3.3
      - 4.4.4.4
      - 5.5.5.5
    password: secret
    server: lb.mydomain.com
    state: present
    user: admin
  delegate_to: localhost
'''

RETURN = r'''
description:
  description: The new description of the address list.
  returned: changed
  type: string
  sample: My address list
addresses:
  description: The new list of addresses applied to the address list.
  returned: changed
  type: list
  sample: [1.1.1.1, 2.2.2.2]
address_ranges:
  description: The new list of address ranges applied to the address list.
  returned: changed
  type: list
  sample: [1.1.1.1-2.2.2.2, 3.3.3.3-4.4.4.4]
address_lists:
  description: The new list of address list names applied to the address list.
  returned: changed
  type: list
  sample: [/Common/list1, /Common/list2]
fqdns:
  description: The new list of FQDN names applied to the address list.
  returned: changed
  type: list
  sample: [google.com, mit.edu]
geo_locations:
  description: The new list of geo locations applied to the address list.
  returned: changed
  type: complex
  contains:
    country:
      description: Country of the geo location.
      returned: changed
      type: string
      sample: US
    region:
      description: Region of the geo location.
      returned: changed
      type: string
      sample: California
'''

import re

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.basic import env_fallback

HAS_DEVEL_IMPORTS = False

try:
    # Sideband repository used for dev
    from library.module_utils.network.f5.bigip import HAS_F5SDK
    from library.module_utils.network.f5.bigip import F5Client
    from library.module_utils.network.f5.common import F5ModuleError
    from library.module_utils.network.f5.common import AnsibleF5Parameters
    from library.module_utils.network.f5.common import cleanup_tokens
    from library.module_utils.network.f5.common import fqdn_name
    from library.module_utils.network.f5.common import f5_argument_spec
    try:
        from library.module_utils.network.f5.common import iControlUnexpectedHTTPError
    except ImportError:
        HAS_F5SDK = False
    HAS_DEVEL_IMPORTS = True
except ImportError:
    # Upstream Ansible
    from ansible.module_utils.network.f5.bigip import HAS_F5SDK
    from ansible.module_utils.network.f5.bigip import F5Client
    from ansible.module_utils.network.f5.common import F5ModuleError
    from ansible.module_utils.network.f5.common import AnsibleF5Parameters
    from ansible.module_utils.network.f5.common import cleanup_tokens
    from ansible.module_utils.network.f5.common import fqdn_name
    from ansible.module_utils.network.f5.common import f5_argument_spec
    try:
        from ansible.module_utils.network.f5.common import iControlUnexpectedHTTPError
    except ImportError:
        HAS_F5SDK = False

try:
    import netaddr
    HAS_NETADDR = True
except ImportError:
    HAS_NETADDR = False


class Parameters(AnsibleF5Parameters):
    api_map = {
        'addressLists': 'address_lists',
        'geo': 'geo_locations'
    }

    api_attributes = [
        'addressLists', 'addresses', 'description', 'fqdns', 'geo'
    ]

    returnables = [
        'addresses', 'address_ranges', 'address_lists', 'description',
        'fqdns', 'geo_locations'
    ]

    updatables = [
        'addresses', 'address_ranges', 'address_lists', 'description',
        'fqdns', 'geo_locations'
    ]

    def to_return(self):
        result = {}
        try:
            for returnable in self.returnables:
                result[returnable] = getattr(self, returnable)
            result = self._filter_params(result)
        except Exception:
            pass
        return result

    def _fqdn_name(self, value):
        if value is not None and not value.startswith('/'):
            return '/{0}/{1}'.format(self.partition, value)
        return value


class ApiParameters(Parameters):
    @property
    def address_ranges(self):
        if self._values['addresses'] is None:
            return None
        result = []
        for address_range in self._values['addresses']:
            if '-' not in address_range['name']:
                continue
            result.append(address_range['name'].strip())
        result = sorted(result)
        return result

    @property
    def address_lists(self):
        if self._values['address_lists'] is None:
            return None
        result = []
        for x in self._values['address_lists']:
            item = '/{0}/{1}'.format(x['partition'], x['name'])
            result.append(item)
        result = sorted(result)
        return result

    @property
    def addresses(self):
        if self._values['addresses'] is None:
            return None
        result = [x['name'] for x in self._values['addresses'] if '-' not in x['name']]
        result = sorted(result)
        return result

    @property
    def fqdns(self):
        if self._values['fqdns'] is None:
            return None
        result = [str(x['name']) for x in self._values['fqdns']]
        result = sorted(result)
        return result

    @property
    def geo_locations(self):
        if self._values['geo_locations'] is None:
            return None
        result = [str(x['name']) for x in self._values['geo_locations']]
        result = sorted(result)
        return result


class ModuleParameters(Parameters):
    def __init__(self, params=None):
        super(ModuleParameters, self).__init__(params=params)
        self.country_iso_map = {
            'Afghanistan': 'AF',
            'Albania': 'AL',
            'Algeria': 'DZ',
            'American Samoa': 'AS',
            'Andorra': 'AD',
            'Angola': 'AO',
            'Anguilla': 'AI',
            'Antarctica': 'AQ',
            'Antigua and Barbuda': 'AG',
            'Argentina': 'AR',
            'Armenia': 'AM',
            'Aruba': 'AW',
            'Australia': 'AU',
            'Austria': 'AT',
            'Azerbaijan': 'AZ',
            'Bahamas': 'BS',
            'Bahrain': 'BH',
            'Bangladesh': 'BD',
            'Barbados': 'BB',
            'Belarus': 'BY',
            'Belgium': 'BE',
            'Belize': 'BZ',
            'Benin': 'BJ',
            'Bermuda': 'BM',
            'Bhutan': 'BT',
            'Bolivia': 'BO',
            'Bosnia and Herzegovina': 'BA',
            'Botswana': 'BW',
            'Brazil': 'BR',
            'Brunei': 'BN',
            'Bulgaria': 'BG',
            'Burkina Faso': 'BF',
            'Burundi': 'BI',
            'Cameroon': 'CM',
            'Canada': 'CA',
            'Cape Verde': 'CV',
            'Central African Republic': 'CF',
            'Chile': 'CL',
            'China': 'CN',
            'Christmas Island': 'CX',
            'Cocos Islands': 'CC',
            'Colombia': 'CO',
            'Cook Islands': 'CK',
            'Costa Rica': 'CR',
            'Cuba': 'CU',
            'Curacao': 'CW',
            'Cyprus': 'CY',
            'Czech Republic': 'CZ',
            'Democratic Republic of the Congo': 'CD',
            'Denmark': 'DK',
            'Djibouti': 'DJ',
            'Dominica': 'DM',
            'Dominican Republic': 'DO',
            'Ecuador': 'EC',
            'Egypt': 'EG',
            'Eritrea': 'ER',
            'Estonia': 'EE',
            'Ethiopia': 'ET',
            'Falkland Islands': 'FK',
            'Faroe Islands': 'FO',
            'Fiji': 'FJ',
            'Finland': 'FI',
            'France': 'FR',
            'French Polynesia': 'PF',
            'Gabon': 'GA',
            'Gambia': 'GM',
            'Georgia': 'GE',
            'Germany': 'DE',
            'Ghana': 'GH',
            'Gilbraltar': 'GI',
            'Greece': 'GR',
            'Greenland': 'GL',
            'Grenada': 'GD',
            'Guam': 'GU',
            'Guatemala': 'GT',
            'Guernsey': 'GG',
            'Guinea': 'GN',
            'Guinea-Bissau': 'GW',
            'Guyana': 'GY',
            'Haiti': 'HT',
            'Honduras': 'HN',
            'Hong Kong': 'HK',
            'Hungary': 'HU',
            'Iceland': 'IS',
            'India': 'IN',
            'Indonesia': 'ID',
            'Iran': 'IR',
            'Iraq': 'IQ',
            'Ireland': 'IE',
            'Isle of Man': 'IM',
            'Israel': 'IL',
            'Italy': 'IT',
            'Ivory Coast': 'CI',
            'Jamaica': 'JM',
            'Japan': 'JP',
            'Jersey': 'JE',
            'Jordan': 'JO',
            'Kazakhstan': 'KZ',
            'Laos': 'LA',
            'Latvia': 'LV',
            'Lebanon': 'LB',
            'Lesotho': 'LS',
            'Liberia': 'LR',
            'Libya': 'LY',
            'Liechtenstein': 'LI',
            'Lithuania': 'LT',
            'Luxembourg': 'LU',
            'Macau': 'MO',
            'Macedonia': 'MK',
            'Madagascar': 'MG',
            'Malawi': 'MW',
            'Malaysia': 'MY',
            'Maldives': 'MV',
            'Mali': 'ML',
            'Malta': 'MT',
            'Marshall Islands': 'MH',
            'Mauritania': 'MR',
            'Mauritius': 'MU',
            'Mayotte': 'YT',
            'Mexico': 'MX',
            'Micronesia': 'FM',
            'Moldova': 'MD',
            'Monaco': 'MC',
            'Mongolia': 'MN',
            'Montenegro': 'ME',
            'Montserrat': 'MS',
            'Morocco': 'MA',
            'Mozambique': 'MZ',
            'Myanmar': 'MM',
            'Namibia': 'NA',
            'Nauru': 'NR',
            'Nepal': 'NP',
            'Netherlands': 'NL',
            'Netherlands Antilles': 'AN',
            'New Caledonia': 'NC',
            'New Zealand': 'NZ',
            'Nicaragua': 'NI',
            'Niger': 'NE',
            'Nigeria': 'NG',
            'Niue': 'NU',
            'North Korea': 'KP',
            'Northern Mariana Islands': 'MP',
            'Norway': 'NO',
            'Oman': 'OM',
            'Pakistan': 'PK',
            'Palau': 'PW',
            'Palestine': 'PS',
            'Panama': 'PA',
            'Papua New Guinea': 'PG',
            'Paraguay': 'PY',
            'Peru': 'PE',
            'Philippines': 'PH',
            'Pitcairn': 'PN',
            'Poland': 'PL',
            'Portugal': 'PT',
            'Puerto Rico': 'PR',
            'Qatar': 'QA',
            'Republic of the Congo': 'CG',
            'Reunion': 'RE',
            'Romania': 'RO',
            'Russia': 'RU',
            'Rwanda': 'RW',
            'Saint Barthelemy': 'BL',
            'Saint Helena': 'SH',
            'Saint Kitts and Nevis': 'KN',
            'Saint Lucia': 'LC',
            'Saint Martin': 'MF',
            'Saint Pierre and Miquelon': 'PM',
            'Saint Vincent and the Grenadines': 'VC',
            'Samoa': 'WS',
            'San Marino': 'SM',
            'Sao Tome and Principe': 'ST',
            'Saudi Arabia': 'SA',
            'Senegal': 'SN',
            'Serbia': 'RS',
            'Seychelles': 'SC',
            'Sierra Leone': 'SL',
            'Singapore': 'SG',
            'Sint Maarten': 'SX',
            'Slovakia': 'SK',
            'Slovenia': 'SI',
            'Solomon Islands': 'SB',
            'Somalia': 'SO',
            'South Africa': 'ZA',
            'South Korea': 'KR',
            'South Sudan': 'SS',
            'Spain': 'ES',
            'Sri Lanka': 'LK',
            'Sudan': 'SD',
            'Suriname': 'SR',
            'Svalbard and Jan Mayen': 'SJ',
            'Swaziland': 'SZ',
            'Sweden': 'SE',
            'Switzerland': 'CH',
            'Syria': 'SY',
            'Taiwan': 'TW',
            'Tajikstan': 'TJ',
            'Tanzania': 'TZ',
            'Thailand': 'TH',
            'Togo': 'TG',
            'Tokelau': 'TK',
            'Tonga': 'TO',
            'Trinidad and Tobago': 'TT',
            'Tunisia': 'TN',
            'Turkey': 'TR',
            'Turkmenistan': 'TM',
            'Turks and Caicos Islands': 'TC',
            'Tuvalu': 'TV',
            'U.S. Virgin Islands': 'VI',
            'Uganda': 'UG',
            'Ukraine': 'UA',
            'United Arab Emirates': 'AE',
            'United Kingdom': 'GB',
            'United States': 'US',
            'Uruguay': 'UY',
            'Uzbekistan': 'UZ',
            'Vanuatu': 'VU',
            'Vatican': 'VA',
            'Venezuela': 'VE',
            'Vietnam': 'VN',
            'Wallis and Futuna': 'WF',
            'Western Sahara': 'EH',
            'Yemen': 'YE',
            'Zambia': 'ZM',
            'Zimbabwe': 'ZW'
        }
        self.choices_iso_codes = self.country_iso_map.values()

    def is_valid_hostname(self, host):
        """Reasonable attempt at validating a hostname

        Compiled from various paragraphs outlined here
        https://tools.ietf.org/html/rfc3696#section-2
        https://tools.ietf.org/html/rfc1123

        Notably,
        * Host software MUST handle host names of up to 63 characters and
          SHOULD handle host names of up to 255 characters.
        * The "LDH rule", after the characters that it permits. (letters, digits, hyphen)
        * If the hyphen is used, it is not permitted to appear at
          either the beginning or end of a label

        :param host:
        :return:
        """
        if len(host) > 255:
            return False
        host = host.rstrip(".")
        allowed = re.compile(r'(?!-)[A-Z0-9-]{1,63}(?<!-)$', re.IGNORECASE)
        return all(allowed.match(x) for x in host.split("."))

    @property
    def addresses(self):
        if self._values['addresses'] is None:
            return None
        for x in self._values['addresses']:
            try:
                netaddr.IPAddress(x)
            except netaddr.core.AddrFormatError:
                raise F5ModuleError(
                    "Address {0} must be either an IPv4 or IPv6 address".format(x)
                )
        result = [str(x) for x in self._values['addresses']]
        result = sorted(result)
        return result

    @property
    def address_ranges(self):
        if self._values['address_ranges'] is None:
            return None
        result = []
        for address_range in self._values['address_ranges']:
            start, stop = address_range.split('-')
            start = start.strip()
            stop = stop.strip()

            start = netaddr.IPAddress(start)
            stop = netaddr.IPAddress(stop)
            if start.version != stop.version:
                raise F5ModuleError(
                    "When specifying a range, IP addresses must be of the same type; IPv4 or IPv6."
                )
            if start > stop:
                stop, start = start, stop
            item = '{0}-{1}'.format(str(start), str(stop))
            result.append(item)
        result = sorted(result)
        return result

    @property
    def address_lists(self):
        if self._values['address_lists'] is None:
            return None
        result = []
        for x in self._values['address_lists']:
            item = self._fqdn_name(x)
            result.append(item)
        result = sorted(result)
        return result

    @property
    def fqdns(self):
        if self._values['fqdns'] is None:
            return None
        result = []
        for x in self._values['fqdns']:
            if self.is_valid_hostname(x):
                result.append(x)
            else:
                raise F5ModuleError(
                    "The hostname '{0}' looks invalid.".format(x)
                )
        result = sorted(result)
        return result

    @property
    def geo_locations(self):
        if self._values['geo_locations'] is None:
            return None
        result = []
        for x in self._values['geo_locations']:
            if x['region'] is not None and x['region'].strip() != '':
                tmp = '{0}:{1}'.format(x['country'], x['region'])
            else:
                tmp = x['country']
            result.append(tmp)
        result = sorted(result)
        return result


class Changes(Parameters):
    def to_return(self):
        result = {}
        try:
            for returnable in self.returnables:
                result[returnable] = getattr(self, returnable)
            result = self._filter_params(result)
        except Exception:
            pass
        return result


class ReportableChanges(Changes):
    @property
    def addresses(self):
        result = []
        for item in self._values['addresses']:
            if '-' in item['name']:
                continue
            result.append(item['name'])
        return result

    @property
    def address_ranges(self):
        result = []
        for item in self._values['addresses']:
            if '-' not in item['name']:
                continue
            start, stop = item['name'].split('-')
            start = start.strip()
            stop = stop.strip()

            start = netaddr.IPAddress(start)
            stop = netaddr.IPAddress(stop)
            if start.version != stop.version:
                raise F5ModuleError(
                    "When specifying a range, IP addresses must be of the same type; IPv4 or IPv6."
                )
            if start > stop:
                stop, start = start, stop
            item = '{0}-{1}'.format(str(start), str(stop))
            result.append(item)
        result = sorted(result)
        return result

    @property
    def address_lists(self):
        result = []
        for x in self._values['address_lists']:
            item = '/{0}/{1}'.format(x['partition'], x['name'])
            result.append(item)
        result = sorted(result)
        return result


class UsableChanges(Changes):
    @property
    def addresses(self):
        if self._values['addresses'] is None and self._values['address_ranges'] is None:
            return None
        result = []
        if self._values['addresses']:
            result += [dict(name=str(x)) for x in self._values['addresses']]
        if self._values['address_ranges']:
            result += [dict(name=str(x)) for x in self._values['address_ranges']]
        return result

    @property
    def address_lists(self):
        if self._values['address_lists'] is None:
            return None
        result = []
        for x in self._values['address_lists']:
            partition, name = x.split('/')[1:]
            result.append(dict(
                name=name,
                partition=partition
            ))
        return result


class Difference(object):
    def __init__(self, want, have=None):
        self.want = want
        self.have = have

    def compare(self, param):
        try:
            result = getattr(self, param)
            return result
        except AttributeError:
            return self.__default(param)

    def __default(self, param):
        attr1 = getattr(self.want, param)
        try:
            attr2 = getattr(self.have, param)
            if attr1 != attr2:
                return attr1
        except AttributeError:
            return attr1

    @property
    def addresses(self):
        if self.want.addresses is None:
            return None
        elif self.have.addresses is None:
            return self.want.addresses
        if sorted(self.want.addresses) != sorted(self.have.addresses):
            return self.want.addresses

    @property
    def address_lists(self):
        if self.want.address_lists is None:
            return None
        elif self.have.address_lists is None:
            return self.want.address_lists
        if sorted(self.want.address_lists) != sorted(self.have.address_lists):
            return self.want.address_lists

    @property
    def address_ranges(self):
        if self.want.address_ranges is None:
            return None
        elif self.have.address_ranges is None:
            return self.want.address_ranges
        if sorted(self.want.address_ranges) != sorted(self.have.address_ranges):
            return self.want.address_ranges

    @property
    def fqdns(self):
        if self.want.fqdns is None:
            return None
        elif self.have.fqdns is None:
            return self.want.fqdns
        if sorted(self.want.fqdns) != sorted(self.have.fqdns):
            return self.want.fqdns


class ModuleManager(object):
    def __init__(self, *args, **kwargs):
        self.module = kwargs.get('module', None)
        self.client = kwargs.get('client', None)
        self.want = ModuleParameters(params=self.module.params)
        self.have = ApiParameters()
        self.changes = UsableChanges()

    def _update_changed_options(self):
        diff = Difference(self.want, self.have)
        updatables = Parameters.updatables
        changed = dict()
        for k in updatables:
            change = diff.compare(k)
            if change is None:
                continue
            else:
                if isinstance(change, dict):
                    changed.update(change)
                else:
                    changed[k] = change
        if changed:
            self.changes = UsableChanges(params=changed)
            return True
        return False

    def should_update(self):
        result = self._update_changed_options()
        if result:
            return True
        return False

    def exec_module(self):
        changed = False
        result = dict()
        state = self.want.state

        try:
            if state == "present":
                changed = self.present()
            elif state == "absent":
                changed = self.absent()
        except iControlUnexpectedHTTPError as e:
            raise F5ModuleError(str(e))

        reportable = ReportableChanges(params=self.changes.to_return())
        changes = reportable.to_return()
        result.update(**changes)
        result.update(dict(changed=changed))
        self._announce_deprecations(result)
        return result

    def _announce_deprecations(self, result):
        warnings = result.pop('__warnings', [])
        for warning in warnings:
            self.module.deprecate(
                msg=warning['msg'],
                version=warning['version']
            )

    def present(self):
        if self.exists():
            return self.update()
        else:
            return self.create()

    def exists(self):
        result = self.client.api.tm.security.firewall.address_lists.address_list.exists(
            name=self.want.name,
            partition=self.want.partition
        )
        return result

    def update(self):
        self.have = self.read_current_from_device()
        if not self.should_update():
            return False
        if self.module.check_mode:
            return True
        self.update_on_device()
        return True

    def remove(self):
        if self.module.check_mode:
            return True
        self.remove_from_device()
        if self.exists():
            raise F5ModuleError("Failed to delete the resource.")
        return True

    def create(self):
        self.have = ApiParameters()
        self._update_changed_options()
        if self.module.check_mode:
            return True
        self.create_on_device()
        return True

    def create_on_device(self):
        params = self.changes.api_params()
        self.client.api.tm.security.firewall.address_lists.address_list.create(
            name=self.want.name,
            partition=self.want.partition,
            **params
        )

    def update_on_device(self):
        params = self.changes.api_params()
        resource = self.client.api.tm.security.firewall.address_lists.address_list.load(
            name=self.want.name,
            partition=self.want.partition
        )
        resource.modify(**params)

    def absent(self):
        if self.exists():
            return self.remove()
        return False

    def remove_from_device(self):
        resource = self.client.api.tm.security.firewall.address_lists.address_list.load(
            name=self.want.name,
            partition=self.want.partition
        )
        if resource:
            resource.delete()

    def read_current_from_device(self):
        resource = self.client.api.tm.security.firewall.address_lists.address_list.load(
            name=self.want.name,
            partition=self.want.partition
        )
        result = resource.attrs
        return ApiParameters(params=result)


class ArgumentSpec(object):
    def __init__(self):
        self.supports_check_mode = True
        argument_spec = dict(
            description=dict(),
            name=dict(required=True),
            addresses=dict(type='list'),
            address_ranges=dict(type='list'),
            address_lists=dict(type='list'),
            geo_locations=dict(
                type='list',
                elements='dict',
                options=dict(
                    country=dict(
                        required=True,
                    ),
                    region=dict()
                )
            ),
            fqdns=dict(type='list'),
            partition=dict(
                default='Common',
                fallback=(env_fallback, ['F5_PARTITION'])
            ),
            state=dict(
                default='present',
                choices=['present', 'absent']
            )
        )
        self.argument_spec = {}
        self.argument_spec.update(f5_argument_spec)
        self.argument_spec.update(argument_spec)


def main():
    spec = ArgumentSpec()

    module = AnsibleModule(
        argument_spec=spec.argument_spec,
        supports_check_mode=spec.supports_check_mode
    )
    if not HAS_F5SDK:
        module.fail_json(msg="The python f5-sdk module is required")
    if not HAS_NETADDR:
        module.fail_json(msg="The python netaddr module is required")

    try:
        client = F5Client(**module.params)
        mm = ModuleManager(module=module, client=client)
        results = mm.exec_module()
        cleanup_tokens(client)
        module.exit_json(**results)
    except F5ModuleError as ex:
        cleanup_tokens(client)
        module.fail_json(msg=str(ex))


if __name__ == '__main__':
    main()
