import eventlet

participants = []

def read_chat_forever(writer, reader):
    line = reader.readline()
    while line:
        print "Chat:", line.strip()
        for p in participants:
            if p is not writer: # Don't echo
                p.write(line)
                p.flush()
        line = reader.readline()
    participants.remove(writer)
    print "Participant left chat."

try:
    print "ChatServer starting up on port 3000"
    server = eventlet.listen(('0.0.0.0', 3000))
    while True:
        new_connection, address = server.accept()
        print "Participant joined chat."
        new_writer = new_connection.makefile('w')
        participants.append(new_writer)
        eventlet.spawn_n(read_chat_forever, 
                         new_writer, 
                         new_connection.makefile('r'))
except (KeyboardInterrupt, SystemExit):
    print "ChatServer exiting."
