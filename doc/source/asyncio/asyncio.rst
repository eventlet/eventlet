.. _asyncio-index:

Asyncio in Eventlet
###################

Asyncio Compatibility
=====================

Compatibility between Asyncio and Eventlet has been recently introduced.

You may be interested by the state of the art of this compatibility and by
the potential limitations, so please take a look at
:ref:`asyncio-compatibility`.

Asyncio Hub & Functions
=======================

Discover the :mod:`Asyncio Hub <eventlet.hubs.asyncio>`

You may also want to take a look to the
:mod:`Asyncio compatibility functions <eventlet.asyncio>`.

Migrating from Eventlet to Asyncio
==================================

Why Migrating?
--------------

Eventlet is a broken and outdated technology.

Eventlet was created almost 20 years ago (See the :ref:`history` of Eventlet),
at a time where Python did not provided non-blocking features.

Time passed and Python now provide AsyncIO.

In parallel of the evolution of Python, the maintenance of Eventlet was
discontinued during several versions of Python, increasing the gap between
the monkey patching of Eventlet and the recent implementation of Python.

This gap is now not recoverable. For this reason, we decided to officially
abandon the maintenance of Eventlet in an incremental way.

In a last effort, we want to lead Eventlet to a well deserved rest.
Our goal is to provide you a guide to migrate off of Eventlet and then
to properly retire Eventlet.

For more details about the reasons who motivated this effort we invite the
readers to show the discussions related to this scheduled abandon:

https://review.opendev.org/c/openstack/governance/+/902585

Getting Started
---------------

Want to use Asyncio and Eventlet together or you simply want to migrate
off of Eventlet?

Follow the :ref:`official migration guide <migration-guide>`.

We encourage readers to first look at the :ref:`glossary_guide` to
learn about the various terms that may be encountered during the migration.

Alternatives & Tips
-------------------

You want to refactor your code to replace Eventlet usages? See the proposed
alternatives and tips:

- :ref:`awaitlet_alternative`
- :ref:`manage-your-deprecations`
