from eventlet.twisteds import basic

conn = basic.connectTCP('www.google.com', 80, buffer_class=basic.line_only_receiver)
conn.write('GET / HTTP/1.0\r\n\r\n')
for line in conn:
    print line

