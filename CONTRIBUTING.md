# Contributing to Eventlet

Please take a moment to review this document in order to make the contribution
process easy and effective for everyone involved.

Following these guidelines helps to communicate that you respect the time
of the developers managing and developing this open source project. In return,
they should reciprocate that respect in addressing your issue or assessing
patches and features.


## Using the issue tracker

The [issue tracker](https://github.com/eventlet/eventlet/issues) is
the preferred channel for [Discussion](#discussion), [bug reports](#bugs), [features requests](#features)
and [submitting pull requests](#pull-requests).

<a name="discussion"></a>
## Discussion

- There's an IRC channel dedicated to Eventlet: `#eventlet` on freenode. It's a pretty chill place to hang out!
- We have Eventlet Google+ Community. Join us, +1, share your ideas, report bugs, find new friends or even new job!

<a name="bugs"></a>
## Bug reports

A bug is a _demonstrable problem_ that is caused by the code in the repository.
Good bug reports are extremely helpful - thank you!

You may report bugs via GitHub https://github.com/eventlet/eventlet/issues/new

Guidelines for bug reports:

1. **Before filing issue try to search for solution on the web** &mdash; There are lots of good resources for Eventlet and its related information which can be helpful in resolving issues and get things done.
   

2. **Use the GitHub issue search** &mdash; check if the issue has already been
   reported.

3. **Check if the issue has been fixed** &mdash; try to reproduce it using the
   latest `master` or development branch in the repository.

4. Please be sure to report bugs [as effectively as possible](http://www.chiark.greenend.org.uk/~sgtatham/bugs.html),
   to ensure that we understand and act on them quickly.

A good bug report shouldn't leave others needing to chase you up for more information.

Please try to be as detailed as possible in your report.


- What is your environment? 
- Which is eventlet version your using? 
- `uname -a`
- `python -V`
- `pip freeze` 
-  What steps will reproduce the issue? 
-  What would you expect to be the outcome? 

All these details will help people to fix any potential bugs.

Example of good bug report::

> Short description in title of issue like `HTTPS/SSL failure when using requests library on Python 3.4`
>
> `uname -a` output
>
> `python -V` output
> 
> Steps to reproduce issue 

<a name="features"></a>
## Feature requests

Feature requests are welcome. But take a moment to find out whether your idea
fits with the scope and aims of the project. It's up to *you* to make a strong
case to convince the project's developers of the merits of this feature. Please
provide as much detail and context as possible.


<a name="pull-requests"></a>
## Pull requests

Good pull requests - patches, improvements, new features - are a fantastic help.
They should remain focused in scope and avoid containing unrelated commits.

**Please ask first** before embarking on any significant pull request (e.g.
implementing features, re-factoring code), otherwise you risk spending a lot of
time working on something that the project's developers might not want to merge
into the project.

Please adhere to the coding conventions used throughout a project (indentation,
accurate comments, etc.) and any other requirements such as 

- Test is required
- One commit is strongly preferred, except for very big changes
- Commit message should follow the following formula:

>subsystem: description of why the change is useful
>
>optional details
>
>links to related issues or websites

The why part is very important. Diff already says what you have done. But nobody knows why.
Feel free to append yourself into AUTHORS file, sections Thanks To or Contributors.

If you don't like these rules, raw patches are more than welcome!

**IMPORTANT**: By submitting a patch, you agree to allow the project owner to
license your work under the same license as that used by the project.
