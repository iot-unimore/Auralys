#!/usr/bin/bash

rm -rf ./build

~/bin/uncrustify -c ./auralys-uncrustify.cfg ./*.ino --replace --no-backup

chmod 644 ./*.ino
