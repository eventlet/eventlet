from eventlet.twisteds import basic

conn = basic.connectTCP(basic.line_only_receiver, 'www.google.com', 80)
conn.send('GET / HTTP/1.0\r\n\r\n')
for line in conn:
    print line

