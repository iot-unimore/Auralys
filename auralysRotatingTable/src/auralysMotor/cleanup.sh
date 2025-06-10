#!/usr/bin/bash

rm -rf ./build

~/bin/uncrustify -c ./uncrustify.cfg ./*.ino --replace --no-backup

chmod 644 ./*.ino
