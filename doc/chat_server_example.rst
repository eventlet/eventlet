Chat Server Example
---------------------

Let's look at a simple example, a chat server::

 from eventlet import api
 
 participants = [ ]
 
 def read_chat_forever(writer, reader):
     line = reader.readline()
     while line:
         print "Chat:", line.strip()
         for p in participants:
             if p is not writer: # Don't echo
                 p.write(line)
         line = reader.readline()
     participants.remove(writer)
     print "Participant left chat."
 
 try:
     print "ChatServer starting up on port 3000"
     server = api.tcp_listener(('0.0.0.0', 3000))
     while True:
         new_connection, address = server.accept()
         print "Participant joined chat."
         new_writer = new_connection.makefile('w')
         participants.append(new_writer)
         api.spawn(read_chat_forever, new_writer, new_connection.makefile('r'))
 except KeyboardInterrupt:
     print "ChatServer exiting."

The server shown here is very easy to understand. If it was written using Python's threading module instead of eventlet, the control flow and code layout would be exactly the same. The call to ``api.tcp_listener`` would be replaced with the appropriate calls to Python's built-in ``socket`` module, and the call to ``api.spawn`` would be replaced with the appropriate call to the ``thread`` module. However, if implemented using the ``thread`` module, each new connection would require the operating system to allocate another 8 MB stack, meaning this simple program would consume all of the RAM on a machine with 1 GB of memory with only 128 users connected, without even taking into account memory used by any objects on the heap! Using eventlet, this simple program should be able to accommodate thousands and thousands of simultaneous users, consuming very little RAM and very little CPU.

What sort of servers would require concurrency like this? A typical Web server might measure traffic on the order of 10 requests per second; at any given moment, the server might only have a handful of HTTP connections open simultaneously. However, a chat server, instant messenger server, or multiplayer game server will need to maintain one connection per connected user to be able to send messages to them as other users chat or make moves in the game. Also, as advanced Web development techniques such as Ajax, Ajax polling, and Comet (the "Long Poll") become more popular, Web servers will need to be able to deal with many more simultaneous requests. In fact, since the Comet technique involves the client making a new request as soon as the server closes an old one, a Web server servicing Comet clients has the same characteristics as a chat or game server: one connection per connected user. 