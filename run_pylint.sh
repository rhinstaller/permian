#!/bin/bash -ex
PYTHONPATH=$PYTHONPATH:$(pwd) pylint-3 -E --load-plugins libpermian.plugins.pylint_hook libpermian $(python3 -m libpermian.plugins list --paths)
