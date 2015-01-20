#!/bin/bash

set -e

yum check-update
yum install -y http://dl.fedoraproject.org/pub/epel/6/x86_64/epel-release-6-8.noarch.rpm || true
yum install -y python-boto
yum install -y deltarpm python-deltarpm
