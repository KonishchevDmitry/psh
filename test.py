#!/usr/bin/env python

import process

import pycl.log
pycl.log.setup(debug_mode = True)

process.date() | process.grep("MSK 2012") | process.head()
