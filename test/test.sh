#!/bin/bash

set -e

DIR=$( cd "$( dirname "$0" )" && pwd )
ROOT_DIR="$(dirname "$DIR")"

# used to get .rpmmacros and .gnupg
HOME="$DIR"

$ROOT_DIR/bin/rpm-s3 -b ${BUCKET:="pkgr-development-rpm"} -v -p gh/crohr/test/centos6/master --sign --keep 1000 ${DIR}/*.rpm

echo "DONE"
