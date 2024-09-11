.. _manage-your-deprecations:

Manage Your Deprecations
========================

Libraries or applications may have specific features who are strongly related
to Eventlet, like the ``heartbeat_in_pthread`` feature in
the Opentack `oslo.messaging
<https://docs.openstack.org/oslo.messaging/latest/configuration/opts.html#oslo_messaging_rabbit.heartbeat_in_pthread>`_
deliverable.

Migrating off of Eventlet would make these features obsolete. As this kind of
feature expose configuration endpoints people would have to deprecate them to
allow your users to update their config files accordingly. However, the
deprecation process would take several months or even numerous versions before
hoping to see these features removed. Hence blocking the migration.

The proposed solution is to mock these features with empty entrypoints
who will only raise deprecation warnings to inform your users that they have
to update their config files. After 1 or 2 new versions these empty mocks
could be safely removed without impacting anybody.

In other words, these feature will remain in the code, but they will do
nothing. They will be empty feature allowing us to migrate properly.

Example with the ``heartbeat_in_pthread`` feature, by using Asyncio
we wouldn't have to run heartbeats in a separated threads. This feature,
the RabbitMQ heartbeat, would be run in a coroutine. A coroutine who is
ran in the main native thread. The config option will remain available but
it will only show a deprecation warning like the following one::

    __main__:1: DeprecationWarning: Using heartbeat_in_pthread is
    deprecated and will be removed in {SERIES}. Enabling that feature
    have no functional effects due to recent changes applied in the
    networking model used by oslo.messaging. Please plan an update of your
    configuration.
