"""
Test availabilty of AF_INET6 on a machine

Uses socket API to determine configuration
"""

from socket import *

def check_ipv6_lo_addr():
    try:
        sock = socket(AF_INET6, SOCK_STREAM)
        sock.bind(('::1', 0))
        return True
    except:
        return False

def check_ipv6_hosts_file():
    if not check_ipv6_lo_addr():
        return False
    addrinfo = getaddrinfo(gethostname(), 0)
    if (addrinfo[0][0] == AF_INET6):
        return True
    return False

core_use_ipv6_lo_addr = check_ipv6_lo_addr()
use_ipv6_by_default = check_ipv6_hosts_file()

ip_defaults = {}

if core_use_ipv6_lo_addr:
    ip_defaults['core_lo_addr'] = '::1'
    ip_defaults['core_af_inet'] = AF_INET6
else:
    ip_defaults['core_lo_addr'] = '127.0.0.1'
    ip_defaults['core_af_inet'] = AF_INET

if use_ipv6_by_default:
    ip_defaults['af_inet'] = AF_INET6
    ip_defaults['null_addr'] = '::'
    ip_defaults['null_cidr'] = '::/0'
    ip_defaults['lo_addr'] = '::1'
else:
    ip_defaults['af_inet'] = AF_INET
    ip_defaults['null_addr'] = '0.0.0.0'
    ip_defaults['null_cidr'] = '0.0.0.0/0'
    ip_defaults['lo_addr'] = '127.0.0.1'
