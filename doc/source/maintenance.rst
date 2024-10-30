.. _maintenance_process:

Maintenance Process
###################

This section provide guidances and process to eventlet
maintainers. They are mostly dedicated to Eventlet' core maintainers lead the
life cycle of eventlet.

Releases
========

Here we describe the process we usually follow to
process a new release.

1. Create a github issue to track the release
---------------------------------------------

The first step will be to `open a new github issue`_
to warn other maintainers about our intention
to produce a new release. They may want, or not,
to land a specific patch to address a specific
topic. This issue will allow them to raise their
concerns.

Here are some `previous examples of issues`_ specifically
created to handle the release process. Usually we name this
kind of issue with the following pattern "[release] eventlet <next-version-number>".

Please add the `release` label to this issue. It would
ease the tracking of works related to releases.

2. Prepare the changelog
------------------------

You now have to update the changelog by updating
the `NEWS` file available at the root of eventlet the project.

We would recommand to give the big picture of the changes
landed by the coming version. The goal here is not to list
each commit, but rather, to give a summarize of the significant
changes made during this versions.

Once your changes are done, then propose a pull request.

Please add the `changelog` label to this pull request. It would
ease the tracking of works related to releases.

If you want, you can use the issue previously created to list
each commits landed in this new version. Here is an example https://github.com/eventlet/eventlet/issues/897.

3. Create the tag
-----------------

Once the changelog patch is merged, then we are now
able to produce the new corresponding tag, here are the
commands we use to do that:

```bash
$ git fetch origin # get the latest updates from the remote repo
$ git tag -s vX.Y.Z origin/master # create a signed tag where X.Y.Z correspond to the version you are eager to produce
$ git push origin --tags
```

Do not hesitate to provide the list of changes in the tags message.
Here is an example https://github.com/eventlet/eventlet/releases/tag/v0.34.3
You can simply reuse the changelog you made previously.

Alternatively, the Github UI also allow you creating tags.

4. Final checks
---------------

Pushing the previous will produce a new build. This
build will generate our release and will push this
new version to Pypi.

You should ensure that this new version is now
well available on Pypi https://pypi.org/project/eventlet/#history.

Your tag should be listed there https://github.com/eventlet/eventlet/tags.

5. Close the issue
------------------

If the previous steps were successful, then you can
now update the Github issue that you previously created.

I'd recommend to put a comment with the pypi link and the tag link
like there https://github.com/eventlet/eventlet/issues/875#issuecomment-1887435752.

You can now close this Github issue.

.. _open a new github issue: https://github.com/eventlet/eventlet/issues/new
.. _previous examples of issues: https://github.com/eventlet/eventlet/issues?q=label%3Arelease+is%3Aclosed
