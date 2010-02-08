Greening The World
==================

One of the challenges of writing a library like Eventlet is that the built-in networking libraries don't natively support the sort of cooperative yielding that we need.  What we must do instead is patch standard library modules in certain key places so that they do cooperatively yield.  We've in the past considered doing this automatically upon importing Eventlet, but have decided against that course of action because it is un-Pythonic to change the behavior of module A simply by importing module B.

Therefore, the application using Eventlet must explicitly green the world for itself, using one or both of the convenient methods provided.

Import Green
--------------

The first way of greening an application is to import networking-related libraries from the ``eventlet.green`` package.  It contains libraries that have the same interfaces as common standard ones, but they are modified to behave well with green threads.  Using this method is a good engineering practice, because the true dependencies are apparent in every file::

  from eventlet.green import socket
  from eventlet.green import threading
  from eventlet.green import asyncore
  
This works best if every library can be imported green in this manner.  If ``eventlet.green`` lacks a module (for example, non-python-standard modules), then the :mod:`eventlet.patcher` module can come to the rescue.  It provides a function, :func:`eventlet.patcher.import_patched`, that greens any module on import.

.. function:: eventlet.patcher.import_patched(module_name, *additional_modules, **kw_additional_modules)

    Imports a module in a greened manner, so that the module's use of networking libraries like socket will use Eventlet's green versions instead.  The only required argument is the name of the module to be imported::
    
        from eventlet import patcher
        httplib2 = patcher.import_patched('httplib2')
        
    Under the hood, it works by temporarily swapping out the "normal" versions of the libraries in sys.modules for an eventlet.green equivalent.  When the import of the to-be-patched module completes, the state of sys.modules is restored.  Therefore, if the patched module contains the statement 'import socket', import_patched will have it reference eventlet.green.socket.  One weakness of this approach is that it doesn't work for late binding (i.e. imports that happen during runtime).  Late binding of imports is fortunately rarely done (it's slow and against `PEP-8 <http://www.python.org/dev/peps/pep-0008/>`_), so in most cases import_patched will work just fine.
    
    One other aspect of import_patched is the ability to specify exactly which modules are patched.  Doing so may provide a slight performance benefit since only the needed modules are imported, whereas import_patched with no arguments imports a bunch of modules in case they're needed.  The *additional_modules* and *kw_additional_modules* arguments are both sequences of name/module pairs.  Either or both can be used::
    
        from eventlet.green import socket
        from eventlet.green import SocketServer        
        BaseHTTPServer = patcher.import_patched('BaseHTTPServer',
                                ('socket', socket),
                                ('SocketServer', SocketServer))
        BaseHTTPServer = patcher.import_patched('BaseHTTPServer',
                                socket=socket, SocketServer=SocketServer)


Monkeypatching the Standard Library
----------------------------------------

The other way of greening an application is simply to monkeypatch the standard
library.  This has the disadvantage of appearing quite magical, but the advantage of avoiding the late-binding problem.

.. function:: eventlet.patcher.monkey_patch(os=True, select=True, socket=True, thread=True, time=True)

    By default, this function monkeypatches the key system modules by replacing their key elements with green equivalents.  The keyword arguments afford some control over which modules are patched, in case that's important.  For almost all of them, they patch the single module of the same name (e.g. time=True means that the time module is patched [time.sleep is patched by eventlet.sleep]).  The exceptions to this rule are *socket*, which also patches the :mod:`ssl` module if present; and *thread*, which patches both :mod:`thread` and :mod:`Queue`.
    
    It is important to call :func:`eventlet.patcher.monkey_patch` as early in the lifetime of the application as possible.  Try to do it as one of the first lines in the main module.  The reason for this is that sometimes there is a class that inherits from a class that needs to be greened -- e.g. a class that inherits from socket.socket -- and inheritance is done at import time, so therefore the monkeypatching should happen before the module that has the derived class is imported.