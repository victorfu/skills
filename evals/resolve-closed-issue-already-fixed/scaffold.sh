#!/bin/sh
set -e
sh "$(dirname "$0")/../_fixtures/scaffold-shop.sh" --fixed issue-57-closed.json
