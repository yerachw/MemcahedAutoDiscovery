#!/usr/bin/env bash

#https://stackoverflow.com/questions/13940404/whats-the-simplest-way-to-get-a-dump-of-all-memcached-keys-into-a-file

while read -r key; do
    [ -f "$key" ] || echo "get $key" | nc scale-test.lngr6x.0001.use1.cache.amazonaws.com 11211 > "$key.dump";
done < <(memdump --server scale-test.lngr6x.0001.use1.cache.amazonaws.com)