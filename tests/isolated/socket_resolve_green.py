__test__ = False

if __name__ == '__main__':
    import eventlet
    eventlet.monkey_patch(all=True)
    import socket
    import time
    import dns.message
    import dns.query

    def slow_udp(q, *a, **kw):
        addr = '0.0.0.1'
        if 'host2' in str(q.question):
            addr = '0.0.0.2'
        if 'host3' in str(q.question):
            addr = '0.0.0.3'
        r = dns.message.make_response(q)
        r.index = None
        r.flags = 256
        r.answer.append(dns.rrset.from_text(str(q.question[0].name), 60, 'IN', 'A', addr))
        r.time = 0.001
        eventlet.sleep(0.1)
        return r

    dns.query.udp = slow_udp
    results = {}

    def fun(name):
        try:
            results[name] = socket.gethostbyname(name)
        except socket.error as e:
            print('name: {0} error: {1}'.format(name, e))

    pool = eventlet.GreenPool()
    t1 = time.time()
    pool.spawn(fun, 'eventlet-test-host1.')
    pool.spawn(fun, 'eventlet-test-host2.')
    pool.spawn(fun, 'eventlet-test-host3.')
    pool.waitall()
    td = time.time() - t1
    assert 0.1 <= td < 0.3, 'Resolve time expected: ~0.1s, real: {0:.3f}'.format(td)
    assert results.get('eventlet-test-host1.') == '0.0.0.1'
    assert results.get('eventlet-test-host2.') == '0.0.0.2'
    assert results.get('eventlet-test-host3.') == '0.0.0.3'
    print('pass')
