__test__ = False

if __name__ == '__main__':
    import os
    assert os.environ.get('PYTHONHTTPSVERIFY', '') == '0'

    import eventlet
    from eventlet.green import socket, ssl, httplib
    import tests
    sock = ssl.wrap_socket(
        socket.socket(),
        tests.private_key_file,
        tests.certificate_file,
        server_side=True,
    )
    sock.bind(('localhost', 0))
    sock.listen(2)

    @eventlet.spawn
    def https_server():
        client, _ = sock.accept()
        client.read()
        client.sendall(b'HTTP/1.0 204 OK BUT NO THANKS\r\n\r\n')
        eventlet.sleep(0.1)
        client.shutdown(socket.SHUT_RDWR)

    sa = sock.getsockname()
    conn = httplib.HTTPSConnection(sa[0], sa[1], timeout=0.5)
    conn.request('GET', '/')
    r = conn.getresponse()
    r.read()
    assert r.status == '204 OK BUT NO THANKS'

    print('pass')
