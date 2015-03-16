'''greendns - non-blocking DNS support for Eventlet
'''

# Portions of this code taken from the gogreen project:
#   http://github.com/slideinc/gogreen
#
# Copyright (c) 2005-2010 Slide, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above
#       copyright notice, this list of conditions and the following
#       disclaimer in the documentation and/or other materials provided
#       with the distribution.
#     * Neither the name of the author nor the names of other
#       contributors may be used to endorse or promote products derived
#       from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
import struct

from eventlet import patcher
from eventlet.green import _socket_nodns
from eventlet.green import os
from eventlet.green import time
from eventlet.green import select
from eventlet.support import six


dns = patcher.import_patched('dns',
                             select=select,
                             time=time,
                             os=os,
                             socket=_socket_nodns)
dns.resolver = patcher.import_patched('dns.resolver',
                                      select=select,
                                      time=time,
                                      os=os,
                                      socket=_socket_nodns)

for pkg in ('dns.entropy', 'dns.inet', 'dns.query'):
    setattr(dns, pkg.split('.')[1], patcher.import_patched(pkg,
                                                           select=select,
                                                           time=time,
                                                           os=os,
                                                           socket=_socket_nodns))
import dns.rdtypes
for pkg in ['dns.rdtypes.IN', 'dns.rdtypes.ANY']:
    setattr(dns.rdtypes, pkg.split('.')[-1], patcher.import_patched(pkg))
for pkg in ['dns.rdtypes.IN.A', 'dns.rdtypes.IN.AAAA']:
    setattr(dns.rdtypes.IN, pkg.split('.')[-1], patcher.import_patched(pkg))
for pkg in ['dns.rdtypes.ANY.CNAME']:
    setattr(dns.rdtypes.ANY, pkg.split('.')[-1], patcher.import_patched(pkg))


socket = _socket_nodns

DNS_QUERY_TIMEOUT = 10.0
HOSTS_TTL = 10.0

EAI_EAGAIN_ERROR = socket.gaierror(socket.EAI_AGAIN, 'Lookup timed out')
EAI_NODATA_ERROR = socket.gaierror(socket.EAI_NODATA, 'No address associated with hostname')
EAI_NONAME_ERROR = socket.gaierror(socket.EAI_NONAME, 'Name or service not known')


def is_ipv4_addr(host):
    """Return True if host is a valid IPv4 address"""
    if not isinstance(host, six.string_types):
        return False
    try:
        dns.ipv4.inet_aton(host)
    except dns.exception.SyntaxError:
        return False
    else:
        return True


def is_ipv6_addr(host):
    """Return True if host is a valid IPv6 address"""
    if not isinstance(host, six.string_types):
        return False
    try:
        dns.ipv6.inet_aton(host)
    except dns.exception.SyntaxError:
        return False
    else:
        return True


def is_ip_addr(host):
    """Return True if host is a valid IPv4 or IPv6 address"""
    return is_ipv4_addr(host) or is_ipv6_addr(host)


class HostsAnswer(dns.resolver.Answer):
    """Answer class for HostsResolver object"""

    def __init__(self, qname, rdtype, rdclass, rrset, raise_on_no_answer=True):
        """Create a new answer

        :qname: A dns.name.Name instance of the query name
        :rdtype: The rdatatype of the query
        :rdclass: The rdataclass of the query
        :rrset: The dns.rrset.RRset with the response, must have ttl attribute
        :raise_on_no_answer: Whether to raise dns.resolver.NoAnswer if no
           answer.
        """
        self.response = None
        self.qname = qname
        self.rdtype = rdtype
        self.rdclass = rdclass
        self.canonical_name = qname
        if not rrset and raise_on_no_answer:
            raise dns.resolver.NoAnswer()
        self.rrset = rrset
        self.expiration = (time.time() +
                           rrset.ttl if hasattr(rrset, 'ttl') else 0)


class HostsResolver(object):
    """Class to parse the hosts file

    Attributes
    ----------

    :fname: The filename of the hosts file in use.
    :interval: The time between checking for hosts file modification
    """

    def __init__(self, fname=None, interval=HOSTS_TTL):
        self._v4 = {}           # name -> ipv4
        self._v6 = {}           # name -> ipv6
        self._aliases = {}      # name -> cannonical_name
        self.interval = interval
        self.fname = fname
        if fname is None:
            if os.name == 'posix':
                self.fname = '/etc/hosts'
            elif os.name == 'nt':
                self.fname = os.path.expandvars(
                    r'%SystemRoot%\system32\drivers\etc\hosts')
        self._last_load = 0
        if self.fname:
            self._load()

    def _readlines(self):
        """Read the contents of the hosts file

        Return list of lines, comment lines and empty lines are
        excluded.

        Note that this performs disk I/O so can be blocking.
        """
        lines = []
        try:
            with open(self.fname, 'rU') as fp:
                for line in fp:
                    line = line.strip()
                    if line and line[0] != '#':
                        lines.append(line)
        except (IOError, OSError):
            pass
        return lines

    def _load(self):
        """Load hosts file

        This will unconditionally (re)load the data from the hosts
        file.
        """
        lines = self._readlines()
        self._v4.clear()
        self._v6.clear()
        self._aliases.clear()
        for line in lines:
            parts = line.split()
            if len(parts) < 2:
                continue
            ip = parts.pop(0)
            if is_ipv4_addr(ip):
                ipmap = self._v4
            elif is_ipv6_addr(ip):
                if ip.startswith('fe80'):
                    # Do not use link-local addresses, OSX stores these here
                    continue
                ipmap = self._v6
            else:
                continue
            cname = parts.pop(0)
            ipmap[cname] = ip
            for alias in parts:
                ipmap[alias] = ip
                self._aliases[alias] = cname
        self._last_load = time.time()

    def query(self, qname, rdtype=dns.rdatatype.A, rdclass=dns.rdataclass.IN,
              tcp=False, source=None, raise_on_no_answer=True):
        """Query the hosts file

        The known rdtypes are dns.rdatatype.A, dns.rdatatype.AAAA and
        dns.rdatatype.CNAME.

        The ``rdclass`` parameter must be dns.rdataclass.IN while the
        ``tcp`` and ``source`` parameters are ignored.

        Return a HostAnswer instance or raise a dns.resolver.NoAnswer
        exception.
        """
        now = time.time()
        if self._last_load + self.interval < now:
            self._load()
        rdclass = dns.rdataclass.IN
        if isinstance(qname, six.string_types):
            name = qname
            qname = dns.name.from_text(qname)
        else:
            name = str(qname)
        rrset = dns.rrset.RRset(qname, rdclass, rdtype)
        rrset.ttl = self._last_load + self.interval - now
        if rdclass == dns.rdataclass.IN and rdtype == dns.rdatatype.A:
            addr = self._v4.get(name)
            if not addr and qname.is_absolute():
                addr = self._v4.get(name[:-1])
            if addr:
                rrset.add(dns.rdtypes.IN.A.A(rdclass, rdtype, addr))
        elif rdclass == dns.rdataclass.IN and rdtype == dns.rdatatype.AAAA:
            addr = self._v6.get(name)
            if not addr and qname.is_absolute():
                addr = self._v6.get(name[:-1])
            if addr:
                rrset.add(dns.rdtypes.IN.AAAA.AAAA(rdclass, rdtype, addr))
        elif rdclass == dns.rdataclass.IN and rdtype == dns.rdatatype.CNAME:
            cname = self._aliases.get(name)
            if not cname and qname.is_absolute():
                cname = self._aliases.get(name[:-1])
            if cname:
                rrset.add(dns.rdtypes.ANY.CNAME.CNAME(
                    rdclass, rdtype, dns.name.from_text(cname)))
        return HostsAnswer(qname, rdtype, rdclass, rrset, raise_on_no_answer)

    def getaliases(self, hostname):
        """Return a list of all the aliases of a given cname"""
        # Due to the way store aliases this is a bit inefficient, this
        # clearly was an afterthought.  But this is only used by
        # gethostbyname_ex so it's probably fine.
        aliases = []
        if hostname in self._aliases:
            cannon = self._aliases[hostname]
        else:
            cannon = hostname
        aliases.append(cannon)
        for alias, cname in six.iteritems(self._aliases):
            if cannon == cname:
                aliases.append(alias)
        aliases.remove(hostname)
        return aliases


class ResolverProxy(object):
    """Resolver class which can also use /etc/hosts

    Initialise with a HostsResolver instance in order for it to also
    use the hosts file.
    """

    def __init__(self, hosts_resolver=None, filename='/etc/resolv.conf'):
        """Initialise the resolver proxy

        :param hosts_resolver: An instance of HostsResolver to use.

        :param filename: The filename containing the resolver
           configuration.  The default value is correct for both UNIX
           and Windows, on Windows it will result in the configuration
           being read from the Windows registry.
        """
        self._hosts = hosts_resolver
        self._filename = filename
        self._resolver = dns.resolver.Resolver(filename=self._filename)
        self._resolver.cache = dns.resolver.LRUCache()

    def clear(self):
        self._resolver = dns.resolver.Resolver(filename=self._filename)
        self._resolver.cache = dns.resolver.Cache()

    def query(self, qname, rdtype=dns.rdatatype.A, rdclass=dns.rdataclass.IN,
              tcp=False, source=None, raise_on_no_answer=True):
        """Query the resolver, using /etc/hosts if enabled"""
        if qname is None:
            qname = '0.0.0.0'
        if rdclass == dns.rdataclass.IN and self._hosts:
            try:
                return self._hosts.query(qname, rdtype)
            except dns.resolver.NoAnswer:
                pass
        return self._resolver.query(qname, rdtype, rdclass,
                                    tcp, source, raise_on_no_answer)

    def getaliases(self, hostname):
        """Return a list of all the aliases of a given hostname"""
        if self._hosts:
            aliases = self._hosts.getaliases(hostname)
        else:
            aliases = []
        while True:
            try:
                ans = self._resolver.query(hostname, dns.rdatatype.CNAME)
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                break
            else:
                aliases.extend(str(rr.target) for rr in ans.rrset)
                hostname = ans[0].target
        return aliases


resolver = ResolverProxy(hosts_resolver=HostsResolver())


def resolve(name, family=socket.AF_INET, raises=True):
    """Resolve a name for a given family using the global resolver proxy

    This method is called by the global getaddrinfo() function.

    Return a dns.resolver.Answer instance.  If there is no answer it's
    rrset will be emtpy.
    """
    if family == socket.AF_INET:
        rdtype = dns.rdatatype.A
    elif family == socket.AF_INET6:
        rdtype = dns.rdatatype.AAAA
    else:
        raise socket.gaierror(socket.EAI_FAMILY,
                              'Address family not supported')
    try:
        try:
            return resolver.query(name, rdtype, raise_on_no_answer=raises)
        except dns.resolver.NXDOMAIN:
            if not raises:
                return HostsAnswer(dns.name.Name(name),
                                   rdtype, dns.rdataclass.IN, None, False)
            raise
    except dns.exception.Timeout:
        raise EAI_EAGAIN_ERROR
    except dns.exception.DNSException:
        raise EAI_NODATA_ERROR


def resolve_cname(host):
    """Return the canonical name of a hostname"""
    try:
        ans = resolver.query(host, dns.rdatatype.CNAME)
    except dns.resolver.NoAnswer:
        return host
    except dns.exception.Timeout:
        raise EAI_EAGAIN_ERROR
    except dns.exception.DNSException:
        raise EAI_NODATA_ERROR
    else:
        return str(ans[0].target)


def getaliases(host):
    """Return a list of for aliases for the given hostname

    This method does translate the dnspython exceptions into
    socket.gaierror exceptions.  If no aliases are available an empty
    list will be returned.
    """
    try:
        return resolver.getaliases(host)
    except dns.exception.Timeout:
        raise EAI_EAGAIN_ERROR
    except dns.exception.DNSException:
        raise EAI_NODATA_ERROR


def _getaddrinfo_lookup(host, family, flags):
    """Resolve a hostname to a list of addresses

    Helper function for getaddrinfo.
    """
    if flags & socket.AI_NUMERICHOST:
        raise EAI_NONAME_ERROR
    addrs = []
    if family == socket.AF_UNSPEC:
        for qfamily in [socket.AF_INET6, socket.AF_INET]:
            answer = resolve(host, qfamily, False)
            if answer.rrset:
                addrs.extend([rr.address for rr in answer.rrset])
    elif family == socket.AF_INET6 and flags & socket.AI_V4MAPPED:
        answer = resolve(host, socket.AF_INET6, False)
        if answer.rrset:
            addrs = [rr.address for rr in answer.rrset]
        if not addrs or flags & socket.AI_ALL:
            answer = resolve(host, socket.AF_INET, False)
            if answer.rrset:
                addrs = ['::ffff:' + rr.address for rr in answer.rrset]
    else:
        answer = resolve(host, family, False)
        if answer.rrset:
            addrs = [rr.address for rr in answer.rrset]
    return str(answer.qname), addrs


def getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
    """Replacement for Python's socket.getaddrinfo

    This does the A and AAAA lookups asynchronously after which it
    calls the OS' getaddrinfo(3) using the AI_NUMERICHOST flag.  This
    flag ensures getaddrinfo(3) does not use the network itself and
    allows us to respect all the other arguments like the native OS.
    """
    if isinstance(host, six.string_types):
        host = host.encode('idna').decode('ascii')
    if host is not None and not is_ip_addr(host):
        qname, addrs = _getaddrinfo_lookup(host, family, flags)
    else:
        qname = host
        addrs = [host]
    aiflags = (flags | socket.AI_NUMERICHOST) & (0xffff ^ socket.AI_CANONNAME)
    res = []
    err = None
    for addr in addrs:
        try:
            ai = socket.getaddrinfo(addr, port, family,
                                    socktype, proto, aiflags)
        except socket.error as e:
            if flags & socket.AI_ADDRCONFIG:
                err = e
                continue
            raise
        res.extend(ai)
    if not res:
        if err:
            raise err
        raise socket.gaierror(socket.EAI_NONAME, 'No address found')
    if flags & socket.AI_CANONNAME:
        if not is_ip_addr(qname):
            qname = resolve_cname(qname).encode('ascii').decode('idna')
        ai = res[0]
        res[0] = (ai[0], ai[1], ai[2], qname, ai[4])
    return res


def gethostbyname(hostname):
    """Replacement for Python's socket.gethostbyname"""
    if is_ipv4_addr(hostname):
        return hostname
    rrset = resolve(hostname)
    return rrset[0].address


def gethostbyname_ex(hostname):
    """Replacement for Python's socket.gethostbyname_ex"""
    if is_ipv4_addr(hostname):
        return (hostname, [], [hostname])
    ans = resolve(hostname)
    aliases = getaliases(hostname)
    addrs = [rr.address for rr in ans.rrset]
    qname = str(ans.qname)
    if qname[-1] == '.':
        qname = qname[:-1]
    return (qname, aliases, addrs)


def getnameinfo(sockaddr, flags):
    """Replacement for Python's socket.getnameinfo.

    Currently only supports IPv4.
    """
    try:
        host, port = sockaddr
    except (ValueError, TypeError):
        if not isinstance(sockaddr, tuple):
            del sockaddr  # to pass a stdlib test that is
            # hyper-careful about reference counts
            raise TypeError('getnameinfo() argument 1 must be a tuple')
        else:
            # must be ipv6 sockaddr, pretending we don't know how to resolve it
            raise EAI_NONAME_ERROR

    if (flags & socket.NI_NAMEREQD) and (flags & socket.NI_NUMERICHOST):
        # Conflicting flags.  Punt.
        raise EAI_NONAME_ERROR

    if is_ipv4_addr(host):
        try:
            rrset = resolver.query(
                dns.reversename.from_address(host), dns.rdatatype.PTR)
            if len(rrset) > 1:
                raise socket.error('sockaddr resolved to multiple addresses')
            host = rrset[0].target.to_text(omit_final_dot=True)
        except dns.exception.Timeout:
            if flags & socket.NI_NAMEREQD:
                raise EAI_EAGAIN_ERROR
        except dns.exception.DNSException:
            if flags & socket.NI_NAMEREQD:
                raise EAI_NONAME_ERROR
    else:
        try:
            rrset = resolver.query(host)
            if len(rrset) > 1:
                raise socket.error('sockaddr resolved to multiple addresses')
            if flags & socket.NI_NUMERICHOST:
                host = rrset[0].address
        except dns.exception.Timeout:
            raise EAI_EAGAIN_ERROR
        except dns.exception.DNSException:
            raise socket.gaierror(
                (socket.EAI_NODATA, 'No address associated with hostname'))

        if not (flags & socket.NI_NUMERICSERV):
            proto = (flags & socket.NI_DGRAM) and 'udp' or 'tcp'
            port = socket.getservbyport(port, proto)

    return (host, port)


def _net_read(sock, count, expiration):
    """coro friendly replacement for dns.query._net_write
    Read the specified number of bytes from sock.  Keep trying until we
    either get the desired amount, or we hit EOF.
    A Timeout exception will be raised if the operation is not completed
    by the expiration time.
    """
    s = ''
    while count > 0:
        try:
            n = sock.recv(count)
        except socket.timeout:
            # Q: Do we also need to catch coro.CoroutineSocketWake and pass?
            if expiration - time.time() <= 0.0:
                raise dns.exception.Timeout
        if n == '':
            raise EOFError
        count = count - len(n)
        s = s + n
    return s


def _net_write(sock, data, expiration):
    """coro friendly replacement for dns.query._net_write
    Write the specified data to the socket.
    A Timeout exception will be raised if the operation is not completed
    by the expiration time.
    """
    current = 0
    l = len(data)
    while current < l:
        try:
            current += sock.send(data[current:])
        except socket.timeout:
            # Q: Do we also need to catch coro.CoroutineSocketWake and pass?
            if expiration - time.time() <= 0.0:
                raise dns.exception.Timeout


def udp(q, where, timeout=DNS_QUERY_TIMEOUT, port=53,
        af=None, source=None, source_port=0, ignore_unexpected=False):
    """coro friendly replacement for dns.query.udp
    Return the response obtained after sending a query via UDP.

    @param q: the query
    @type q: dns.message.Message
    @param where: where to send the message
    @type where: string containing an IPv4 or IPv6 address
    @param timeout: The number of seconds to wait before the query times out.
    If None, the default, wait forever.
    @type timeout: float
    @param port: The port to which to send the message.  The default is 53.
    @type port: int
    @param af: the address family to use.  The default is None, which
    causes the address family to use to be inferred from the form of of where.
    If the inference attempt fails, AF_INET is used.
    @type af: int
    @rtype: dns.message.Message object
    @param source: source address.  The default is the IPv4 wildcard address.
    @type source: string
    @param source_port: The port from which to send the message.
    The default is 0.
    @type source_port: int
    @param ignore_unexpected: If True, ignore responses from unexpected
    sources.  The default is False.
    @type ignore_unexpected: bool"""

    wire = q.to_wire()
    if af is None:
        try:
            af = dns.inet.af_for_address(where)
        except:
            af = dns.inet.AF_INET
    if af == dns.inet.AF_INET:
        destination = (where, port)
        if source is not None:
            source = (source, source_port)
    elif af == dns.inet.AF_INET6:
        destination = (where, port, 0, 0)
        if source is not None:
            source = (source, source_port, 0, 0)

    s = socket.socket(af, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        expiration = dns.query._compute_expiration(timeout)
        if source is not None:
            s.bind(source)
        try:
            s.sendto(wire, destination)
        except socket.timeout:
            # Q: Do we also need to catch coro.CoroutineSocketWake and pass?
            if expiration - time.time() <= 0.0:
                raise dns.exception.Timeout
        while 1:
            try:
                (wire, from_address) = s.recvfrom(65535)
            except socket.timeout:
                # Q: Do we also need to catch coro.CoroutineSocketWake and pass?
                if expiration - time.time() <= 0.0:
                    raise dns.exception.Timeout
            if from_address == destination:
                break
            if not ignore_unexpected:
                raise dns.query.UnexpectedSource(
                    'got a response from %s instead of %s'
                    % (from_address, destination))
    finally:
        s.close()

    r = dns.message.from_wire(wire, keyring=q.keyring, request_mac=q.mac)
    if not q.is_response(r):
        raise dns.query.BadResponse()
    return r


def tcp(q, where, timeout=DNS_QUERY_TIMEOUT, port=53,
        af=None, source=None, source_port=0):
    """coro friendly replacement for dns.query.tcp
    Return the response obtained after sending a query via TCP.

    @param q: the query
    @type q: dns.message.Message object
    @param where: where to send the message
    @type where: string containing an IPv4 or IPv6 address
    @param timeout: The number of seconds to wait before the query times out.
    If None, the default, wait forever.
    @type timeout: float
    @param port: The port to which to send the message.  The default is 53.
    @type port: int
    @param af: the address family to use.  The default is None, which
    causes the address family to use to be inferred from the form of of where.
    If the inference attempt fails, AF_INET is used.
    @type af: int
    @rtype: dns.message.Message object
    @param source: source address.  The default is the IPv4 wildcard address.
    @type source: string
    @param source_port: The port from which to send the message.
    The default is 0.
    @type source_port: int"""

    wire = q.to_wire()
    if af is None:
        try:
            af = dns.inet.af_for_address(where)
        except:
            af = dns.inet.AF_INET
    if af == dns.inet.AF_INET:
        destination = (where, port)
        if source is not None:
            source = (source, source_port)
    elif af == dns.inet.AF_INET6:
        destination = (where, port, 0, 0)
        if source is not None:
            source = (source, source_port, 0, 0)
    s = socket.socket(af, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        expiration = dns.query._compute_expiration(timeout)
        if source is not None:
            s.bind(source)
        try:
            s.connect(destination)
        except socket.timeout:
            # Q: Do we also need to catch coro.CoroutineSocketWake and pass?
            if expiration - time.time() <= 0.0:
                raise dns.exception.Timeout

        l = len(wire)
        # copying the wire into tcpmsg is inefficient, but lets us
        # avoid writev() or doing a short write that would get pushed
        # onto the net
        tcpmsg = struct.pack("!H", l) + wire
        _net_write(s, tcpmsg, expiration)
        ldata = _net_read(s, 2, expiration)
        (l,) = struct.unpack("!H", ldata)
        wire = _net_read(s, l, expiration)
    finally:
        s.close()
    r = dns.message.from_wire(wire, keyring=q.keyring, request_mac=q.mac)
    if not q.is_response(r):
        raise dns.query.BadResponse()
    return r


def reset():
    resolver.clear()

# Install our coro-friendly replacements for the tcp and udp query methods.
dns.query.tcp = tcp
dns.query.udp = udp
