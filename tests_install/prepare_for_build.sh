#!/bin/bash

if which apt-get; then
    apt-get install -y gcc || true
    apt-get install -y make flex bison perl
    apt-get install -y zlib1g-dev || apt-get install -y zlib-devel
    apt-get install -y libicu-dev || true
    apt-get install -y libicu-devel || true
    apt-get install -y pkg-config
    apt-get install -y patch || true
elif which zypper; then
    zypper install -y gcc make flex bison perl
    zypper install -y --force --force-resolution zlib-devel
    zypper install -y --force --force-resolution libicu-devel
    zypper install -y libipc-run-perl
elif which yum; then
    yum install -y gcc make flex bison perl bzip2 zlib-devel libicu-devel patch
    yum install -y perl-devel || true
fi

tar fax "$1"
cd postgres*/
sudo chown -R postgres:postgres .
sudo -u postgres ./configure --without-readline --without-zlib --prefix="$2" || exit $?
