#!/usr/bin/env python
# Follow a file like tail -f.

import time
def follow(thefile):
    thefile.seek(0,2)
    while True:
        line = thefile.readline()
        if not line:
            time.sleep(0.1)
            continue
        yield line

if __name__ == '__main__':
    logfile = open("/var/log/askap/iocade_bmf_pk01.log","r")
    loglines = follow(logfile)
    for line in loglines:
        print line,