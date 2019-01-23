import eventlet

eventlet.monkey_patch()
import socket
import ssl

# import eventlet.green.ssl as ssl
# import eventlet.green.socket as socket

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
wrappedSocket = ssl.wrap_socket(sock)

import requests
print(requests.get('https://www.google.com/').status_code)
