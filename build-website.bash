#!/bin/bash
set -e

build="$PWD/website-build"
usage="Builds eventlet.net website static pages into ${build}.
Requires sphinx-build, git and Github account."

while [ -n "$1" ]; do
	# TODO: parse args
	echo "$usage" >&2
	exit 1
	shift
done

if ! which sphinx-build >/dev/null; then
	echo "sphinx-build not found. Possible solution: pip install sphinx" >&2
	echo "Links: http://sphinx-doc.org/" >&2
	exit 1
fi

if ! git status >/dev/null; then
	echo "git not found. git and Github account are required to update online documentation." >&2
	echo "Links: http://git-scm.com/ https://github.com/" >&2
	exit 1
fi

echo "1. clean"
rm -rf "$build"
mkdir -p "$build/doc"

echo "2. build static pages"
cp doc/real_index.html "$build/index.html"

# -b html -- builder, output mode
# -d dir  -- path to doctrees cache
# -n      -- nit-picky mode (kind of -Wall for gcc)
# -W      -- turns warnings into errors
# -q      -- quiet, emit only warnings and errors
sphinx-build -b html -d "$build/tmp" -n -q "doc" "$build/doc"
rm -rf "$build/tmp"
rm -f "$build/doc/.buildinfo"

echo "3. Updating git branch gh-pages"
source_name=`git rev-parse --abbrev-ref HEAD`
source_id=`git rev-parse --short HEAD`
git branch --track gh-pages origin/gh-pages || true
git checkout gh-pages
git ls-files -z |xargs -0 rm -f
rm -rf "doc"

mv "$build"/* ./
touch ".nojekyll"
echo "eventlet.net" >"CNAME"
rmdir "$build"

echo "4. Commit"
git add -A
git status

read -p "Carefully read git status output above, press Enter to continue or Ctrl+C to abort"
git commit --edit -m "Website built from $source_name $source_id"
