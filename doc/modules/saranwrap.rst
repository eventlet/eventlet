:mod:`saranwrap` -- Running code in separate processes
==================

This is a convenient way of bundling code off into a separate process.  If you are using Python 2.6, the multiprocessing module probably suits your needs better than saranwrap will.

The simplest way to use saranwrap is to wrap a module and then call functions on that module::

 >>> from eventlet import saranwrap
 >>> import time
 >>> s_time = saranwrap.wrap(time)
 >>> timeobj = s_time.gmtime(0)
 >>> timeobj
 saran:(1970, 1, 1, 0, 0, 0, 3, 1, 0)
 >>> timeobj.tm_sec
 0

The objects so wrapped behave as if they are resident in the current process space, but every attribute access and function call is passed over a nonblocking pipe to the child process.  For efficiency, it's best to make as few attribute calls as possible relative to the amount of work being delegated to the child process.

.. automodule:: eventlet.saranwrap
	:members:
	:undoc-members:


Underlying Protocol
-------------------

Saranwrap's remote procedure calls are achieved by intercepting the basic
getattr and setattr calls in a client proxy, which commnicates those
down to the server which will dispatch them to objects in it's process
space.

The basic protocol to get and set attributes is for the client proxy
to issue the command::

 getattr $id $name
 setattr $id $name $value

 getitem $id $item
 setitem $id $item $value
 eq $id $rhs
 del $id

When the get returns a callable, the client proxy will provide a
callable proxy which will invoke a remote procedure call. The command
issued from the callable proxy to server is::

 call $id $name $args $kwargs

If the client supplies an id of None, then the get/set/call is applied
to the object(s) exported from the server.

The server will parse the get/set/call, take the action indicated, and
return back to the caller one of::

 value $val
 callable
 object $id
 exception $excp

To handle object expiration, the proxy will instruct the rpc server to
discard objects which are no longer in use. This is handled by
catching proxy deletion and sending the command::

 del $id

The server will handle this by removing clearing it's own internal
references. This does not mean that the object will necessarily be
cleaned from the server, but no artificial references will remain
after successfully completing. On completion, the server will return
one of::

 value None
 exception $excp

The server also accepts a special command for debugging purposes::

 status

Which will be intercepted by the server to write back::

 status {...}

The wire protocol is to pickle the Request class in this file. The
request class is basically an action and a map of parameters.
