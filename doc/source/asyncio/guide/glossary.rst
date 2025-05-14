.. _glossary_guide:

Glossary
========

This glossary provides a brief description of some of the terms used within
Eventlet in general, and more specifically in the migration context.
The goal of this glossary is to ensure that everybody has the same
understanding of the used terms.

For more information about anything the migration, see the
:ref:`migration-guide`.

.. _glossary-concurrency:

Concurrency
-----------

**Concurrency** is when two or more tasks can start, run, and complete in
overlapping time **periods**. It doesn't necessarily mean they'll ever both be
running **at the same instant**. For example, *multitasking* on a single-core
machine.

.. _glossary-cooperative-multitasking:

Cooperative Multitasking
------------------------

Whenever a **thread** begins sleeping or awaiting network I/O, there is a
chance for another thread to take the **GIL** and execute Python code.
This is **cooperative multitasking**.

.. _glossary-coro:

Coro
----

Using the name **coro** is a common convention in the Python API
documentation. It refers to a coroutine; i.e., strictly speaking, the result
of calling an async def function, and not the function itself.

.. _glossary-coroutine:

Coroutine
---------

**Coroutines** are programs components that allow execution to be suspended
and resumed, generalizing. They have been described as "functions whose
execution you can pause".

.. _glossary-future:

Future
------

A **future** represents a future completion state of some activity and is
managed by the loop. A Future is a special low-level awaitable object that
represents an eventual result of an asynchronous operation.

.. _glossary-greenlet:

Greenlet
--------

A **greenlet** is a lightweight **coroutine** for in-process sequential
concurrent programming (see **concurrency**). You can usually think of
greenlets as cooperatively scheduled **threads**. The major differences are
that since they’re cooperatively scheduled, you are in control of when they
execute, and since they are **coroutines**, many greenlets can exist in a
single native **thread**.

Greenlets are cooperative (see **cooperative multitasking**) and sequential.
This means that when one greenlet is running, no other greenlet can be
running; the programmer is fully in control of when execution switches between
greenlets. In other words ones, when using greenlets, should not expect
**preemptive** behavior.

Greenlet is also the name of a `library
<https://greenlet.readthedocs.io/en/latest/>`_ that provide the greenlet
mechanism. Eventlet is based on the greenlet library.

.. _glossary-green-thread:

Green Thread
------------

A **green thread** is a **threads** that is scheduled by a runtime library
or virtual machine (VM) instead of natively by the underlying operating system
(OS). Green threads emulate multithreaded environments without relying on any
native OS abilities, and they are managed in user space) instead of kernel
space, enabling them to work in environments that do not have native thread
support.

.. _glossary-gil:

Global Interpreter Lock (GIL)
-----------------------------

A **global interpreter lock (GIL**) is a lock used internally to CPython to
ensure that only one **thread** runs in the Python VM at a time. In general,
Python offers to switch among threads only between bytecode instructions (see
**preemptive multitasking** and **cooperative multitasking**). 

.. _glossary-parallelism:

Parallelism
-----------

**Parallelism** is when tasks *literally* run at the same time, e.g., on a
multicore processor. A condition that arises when at least two threads are
executing simultaneously.

.. _glossary-preemptive:

Preemptive/Preemption
---------------------

**Preemption** is the act of temporarily interrupting an executing **task**,
with the intention of resuming it at a later time. This interrupt is done by
an external scheduler with no assistance or cooperation from the task.

.. _glossary-preemptive-multitasking:

Preemptive multitasking
-----------------------

**Preemptive multitasking** involves the use of an interrupt mechanism which
suspends the currently executing process and invokes a scheduler to determine
which process should execute next. Therefore, all processes will get some
amount of CPU time at any given time.

CPython also has **preemptive multitasking**: If a thread runs
uninterrupted for 1000 bytecode instructions in Python 2, or runs 15
milliseconds in Python 3, then it gives up the GIL and another thread may run.

.. _glossary-task:

Task
----

A **task** is a scheduled and independently managed **coroutine**. Tasks are
awaitable objects used to schedule coroutines concurrently.

.. _glossary-thread:

Thread
------

**Threads** are a way for a program to divide (termed "split") itself into two
or more simultaneously (or pseudo-simultaneously) running tasks. Threads and
processes differ from one operating system to another but, in general, a
thread is contained inside a process and different threads in the same process
share same resources while different processes in the same multitasking
operating system do not.

When do threads switch in Python? The switch depends on the context. The
threads may be interrupted (see **preemptive multitasking**) or behave
cooperatively (see **cooperative multitasking**).
