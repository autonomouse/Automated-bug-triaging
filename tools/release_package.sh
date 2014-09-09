#!/bin/bash
# Should be run from top of source tree with local doberman in PYTHONPATH
rm -rf *.egg-info
[[ -n "$(bzr status)" ]] && echo "Repo not clean" && exit 1
distro=${1:-"precise"}
version="$(python -c "import doberman; print doberman.__version__")"
echo $version
bzr_rev=$(bzr revno)
dch -b -D $distro \
  --newversion ${version}~bzr${bzr_rev}~${distro}-0ubuntu1 \
  "PPA build."
debcommit
fakeroot debian/rules get-orig-source
bzr bd -S -- sa
rc=$?
# revert the PPA build changelog entry and revision
bzr uncommit --force
bzr revert
rm -rf *.egg-info
[[ ! $rc ]] && echo "Build failed" && exit 1
echo "Run: dput ppa:oil-ci/oil-ci ../doberman*bzr${bzr_rev}*.changes"
