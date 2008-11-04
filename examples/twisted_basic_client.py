from eventlet.twistedutil.protocol import connectTCP
from eventlet.twistedutil.protocols.basic import LineOnlyReceiverBuffer

conn = connectTCP('www.google.com', 80, buffer_class=LineOnlyReceiverBuffer)
conn.write('GET / HTTP/1.0\r\n\r\n')
for line in conn:
    print line

