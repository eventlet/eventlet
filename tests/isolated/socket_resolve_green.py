__test__ = False

if __name__ == '__main__':
    import eventlet
    eventlet.monkey_patch(all=True)
    import socket
    import time
    from eventlet.support.dns import message as dns_message
    from eventlet.support.dns import query   as dns_query
    from eventlet.support.dns import rrset   as dns_rrset

    n = 10
    delay = 0.01
    addr_map = {'test-host{0}.'.format(i): '0.0.1.{0}'.format(i) for i in range(n)}

    def slow_udp(q, *a, **kw):
        qname = q.question[0].name
        addr = addr_map[qname.to_text()]
        r = dns_message.make_response(q)
        r.index = None
        r.flags = 256
        r.answer.append(dns_rrset.from_text(str(qname), 60, 'IN', 'A', addr))
        r.time = 0.001
        eventlet.sleep(delay)
        return r

    dns_query.tcp = lambda: eventlet.Timeout(0)
    dns_query.udp = slow_udp
    results = {}

    def fun(name):
        try:
            results[name] = socket.gethostbyname(name)
        except socket.error as e:
            print('name: {0} error: {1}'.format(name, e))

    pool = eventlet.GreenPool(size=n + 1)

    # FIXME: For unknown reason, first GreenPool.spawn() takes ~250ms on some platforms.
    # Spawned function executes for normal expected time, it's the GreenPool who needs warmup.
    pool.spawn(eventlet.sleep)

    t1 = time.time()
    for name in addr_map:
        pool.spawn(fun, name)
    pool.waitall()
    td = time.time() - t1
    fail_msg = 'Resolve time expected: ~{0:.3f}s, real: {1:.3f}'.format(delay, td)
    assert delay <= td < delay * n, fail_msg
    assert addr_map == results
    print('pass')
