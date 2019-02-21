#!/usr/bin/env python

import os
import numpy as np
import matplotlib.pyplot as plt
import glob
import subprocess
import sys
import numpy.fft as fft

nsamp_seak = 0
nsamp      = 1

hdrsize    = 4096
dsize      = 4
ndata_samp = 4

#bw         = 336.0
bw         = 231
nchan_chan = 864
c_freq     = 1340.5

nchan_band = int(bw * nchan_chan)
ndata      = ndata_samp * nsamp * nchan_band
freq0      = 1340.5 - bw/2.0
freq       = freq0 + np.arange(int(nchan_band))/float(nchan_chan)

fdir  = "/beegfs/DENG/pacifix8_numa0_process1/"
fname = "2018-08-30-19:37:27_0000000000000000.000000.dada"

blksize = ndata * dsize
fname   = os.path.join(fdir, fname)
f       = open(fname, "r")
f.seek(hdrsize + nsamp_seak * blksize * ndata_samp)
sample  = np.array(np.fromstring(f.read(blksize), dtype='float32'))
sample  = np.reshape(sample, (ndata_samp, nchan_band))

plt.figure()
plt.plot(freq, sample[0,:])
plt.plot(freq, sample[1,:])
plt.plot(freq, sample[2,:])
plt.plot(freq, sample[3,:])
plt.show()

f.close()
