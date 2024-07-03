.. _awaitlet_alternative:

Awaitlet as an Alternative
==========================

Applications with several years of existence may have seen their code base
growing again and again, thus, migrating this kind of existing code
base toward AsyncIO, would be painful or even unrealistic. For most of these
applications, migrating to AsyncIO would may mean a complete rewriting of
these applications.

`Awaitlet <https://awaitlet.sqlalchemy.org/en/latest/>`_ is an alternative
which allow you to migrate this kind of existing code base without getting
the headaches associated to migrating such deliverables.

Awaitlet allows existing programs written to use threads and blocking APIs to
be ported to asyncio, by replacing frontend and backend code with asyncio
compatible approaches, but allowing intermediary code to remain completely
unchanged, with no addition of ``async`` or ``await`` keywords throughout the
entire codebase needed. Its primary use is to support code that is
cross-compatible with asyncio and non-asyncio runtime environments.

Awaitlet is a direct extract of `SQLAlchemy <https://www.sqlalchemy.org/>`_’s
own asyncio mediation layer, with no dependencies on SQLAlchemy. This code has
been in widespread production use in thousands of environments for several
years.

.. warning::

    Using Awaitlet require to use the :mod:`Asyncio Hub
    <eventlet.hubs.asyncio>`

    :ref:`understanding_hubs`

Here is an example of Awaitlet usage::

    import asyncio
    import awaitlet

    def asyncio_sleep():
        return awaitlet.awaitlet(asyncio.sleep(5, result='hello'))

    print(asyncio.run(awaitlet.async_def(asyncio_sleep)))

We invite the reader to read the `Awaitlet synopsis
<https://awaitlet.sqlalchemy.org/en/latest/synopsis.html>`_ to get a better
overview of the opportunities offered by this library.
