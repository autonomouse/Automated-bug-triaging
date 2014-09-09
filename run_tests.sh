#!/bin/bash -e
PROJECT=doberman

if echo "$@" | grep -q "lint" ; then
  echo "Running flake8 lint tests..."
  flake8 --exclude ${PROJECT}/tests/ ${PROJECT} --ignore=F403
  echo "OK"
fi

if echo "$@" | grep -q "unit" ; then
  echo "Running unit tests..."
  /usr/bin/nosetests -v --nologcapture --with-coverage ${PROJECT}/tests/
fi
