#!/usr/bin/env python

import ConfigParser, parser, argparse, socket, struct, json, os, subprocess, threading, datetime, time
import numpy as np

# ./capture.py -a ../config/pipeline.conf -b ../config/system.conf -c 1340.5 -d 336 -e 10.17.0.1:17100:8:0:1:2:3:4:5:6:7 10.17.0.1:17101:8:8:9:10:11:12:13:14:15 10.17.0.1:17102:8:16:17:18:19:20:21:22:23 10.17.0.1:17103:8:24:25:26:27:28:29:30:31 10.17.0.1:17104:8:32:33:34:35:36:37:38:39 10.17.0.1:17105:8:40:41:42:43:44:45:46:47 -f 0 -g 0 -i 0

SECDAY      = 86400.0
DADA_TIMSTR = "%Y-%m-%d-%H:%M:%S"
MJD1970     = 40587.0

def ConfigSectionMap(fname, section):
    # Play with configuration file
    Config = ConfigParser.ConfigParser()
    Config.read(fname)
    
    dict_conf = {}
    options = Config.options(section)
    for option in options:
        try:
            dict_conf[option] = Config.get(section, option)
            if dict_conf[option] == -1:
                DebugPrint("skip: %s" % option)
        except:
            print("exception on %s!" % option)
            dict_conf[option] = None
    return dict_conf

def capture_reftime(destination, pktsz, df_res, system_conf):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = (destination.split(":")[0], int(destination.split(":")[1]))
    sock.bind(server_address)
    buf, address = sock.recvfrom(pktsz) # raw packet
    
    data       = np.fromstring(buf, 'uint64')
    hdr_part   = np.uint64(struct.unpack("<Q", struct.pack(">Q", data[0]))[0])
    sec_epoch  = (hdr_part & np.uint64(0x3fffffff00000000)) >> np.uint64(32)
    df_idf     = hdr_part & np.uint64(0x00000000ffffffff)

    hdr_part   = np.uint64(struct.unpack("<Q", struct.pack(">Q", data[1]))[0])
    epoch      = (hdr_part & np.uint64(0x00000000fc000000)) >> np.uint64(26)
    epoch      = float(ConfigSectionMap(system_conf, "EpochBMF")['{:d}'.format(epoch)])

    sec_prd    = df_idf * df_res
    df_sec     = sec_epoch + np.floor(sec_prd) + epoch * SECDAY  # Int part of seconds from 1970-01-01

    utc_start  = time.strftime(DADA_TIMSTR, time.gmtime(df_sec))    # UTC_START of int part seconds
    mjd_start  = df_sec/SECDAY + MJD1970                            # MJD_START of int part seconds
    
    microseconds = 1.0E6 * (sec_prd - np.floor(sec_prd))
    picoseconds  = int(1E6 * round(microseconds))                # picoseconds of fraction second
        
    return df_sec, df_idf, utc_start, mjd_start, picoseconds
    
def all_connection(destination, pktsz, df_prd):
    nport = len(destination)
    active = np.zeros(nport, dtype = int)
    socket.setdefaulttimeout(df_prd)  # Force to timeout after one data frame period
    
    for i in range(nport):
        active[i] = connection(destination[i].split(":")[0], int(destination[i].split(":")[1]), pktsz)
    destination_active = []   # The destination where we can receive data
    destination_dead   = []   # The destination where we can not receive data
    for i in range(nport):
        if active[i] == 1:
            destination_active.append(destination[i])
        else:
            destination_dead.append(destination[i])
    return destination_active, destination_dead
    
def connection(ip, port, pktsz):
    active = 1
    data = bytearray(pktsz) 
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = (ip, port)
    sock.bind(server_address)
    
    try:
        nbyte, address = sock.recvfrom_into(data, pktsz)
        if (nbyte != pktsz):
            active = 0
    except:
        active = 0
        
    return active

def main(args):
    # Read pipeline input
    args          = parser.parse_args()
    pipeline_conf = args.pipeline_conf[0]
    system_conf   = args.system_conf[0]
    destination   = args.destination
    nchan         = args.nchan[0]
    hdr           = args.hdr[0]
    part          = args.part[0]
    beam          = args.beam[0]
    
    # Get pipeline configuration from configuration file
    ndf_blk      = int(ConfigSectionMap(pipeline_conf, "CAPTURE")['ndf_blk'])
    nblk         = int(ConfigSectionMap(pipeline_conf, "CAPTURE")['nblk'])
    hdr_fname    = ConfigSectionMap(pipeline_conf, "CAPTURE")['hdr_fname']
    key          = format(int("0x{:s}".format(ConfigSectionMap(pipeline_conf, "CAPTURE")['key']), 0), 'x')
    kfile_prefix = ConfigSectionMap(pipeline_conf, "CAPTURE")['kfname_prefix']
    kfname       = "{:s}_beam{:02d}_part{:d}.key".format(kfile_prefix, beam, part)
    nreader      = int(ConfigSectionMap(pipeline_conf, "CAPTURE")['nreader'])
     
    # Record the key to a key file with kfname
    kfile = open(kfname, "w")
    kfile.writelines("DADA INFO:\n")
    kfile.writelines("key {:s}\n".format(key))
    kfile.close()
    
    # Get system configuration from configuration file
    df_prd       = float(ConfigSectionMap(system_conf, "EthernetInterfaceBMF")['df_prd'])
    nsamp_df     = int(ConfigSectionMap(system_conf, "EthernetInterfaceBMF")['nsamp_df'])
    npol_samp    = int(ConfigSectionMap(system_conf, "EthernetInterfaceBMF")['npol_samp'])
    ndim_pol     = int(ConfigSectionMap(system_conf, "EthernetInterfaceBMF")['ndim_pol'])
    nbyte_dim    = int(ConfigSectionMap(system_conf, "EthernetInterfaceBMF")['nbyte_dim'])
    nchan_chk    = int(ConfigSectionMap(system_conf, "EthernetInterfaceBMF")['nchan_chk'])
    df_hdrsz     = int(ConfigSectionMap(system_conf, "EthernetInterfaceBMF")['df_hdrsz'])
    df_res       = float(ConfigSectionMap(system_conf, "EthernetInterfaceBMF")['df_res'])
    pktsz        = npol_samp * ndim_pol * nbyte_dim * nchan_chk * nsamp_df + df_hdrsz
    if hdr == 1:
        blksz     = ndf_blk * (nsamp_df * npol_samp * ndim_pol * nbyte_dim * nchan + df_hdrsz * nchan / nchan_chk)
    else:
        blksz   = ndf_blk * nsamp_df * npol_samp * ndim_pol * nbyte_dim * nchan
    
    # To update the desination for current capture part, which finds out the low frequency chunk, the index of frequency chunk in current capture part and active ports
    chk = []
    for item in destination:
        for i in range(int(item.split(':')[2])):
            chk.append(int(item.split(':')[i + 3]))
    chk = np.array(chk)
    min_chk = min(chk)    
    destination_update = []
    for item in destination:
        temp = "{:s}:{:s}:{:s}".format(item.split(":")[0], item.split(":")[1], item.split(":")[2])
        for i in range(int(item.split(':')[2])):
            temp = "{:s}:{:d}".format(temp, int(item.split(':')[i + 3]) - min_chk)
        destination_update.append(temp)
    
    # Check the connection
    destination_active, destination_dead = all_connection(destination_update, pktsz, df_prd)
    if (len(destination_active) == 0):
        print "There is no active port for beam {:02d}, have to abort ...".format(beam)
        exit(1)
    print destination_active, destination_dead
    
    # Create PSRDADA buffer
    os.system("dada_db -l -p -k {:s} -b {:d} -n {:d} -r {:d}".format(key, blksz, nblk, nreader))

    # Get reference timestamp of capture
    df_sec, df_idf, utc_start, mjd_start, picoseconds = capture_reftime(destination_active[0], pktsz, df_res, system_conf)
    
    # Delete PSRDADA buffer
    os.system("dada_db -d {:s}".format(key))
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Create DADA buffer and run capture with given parameters')
    parser.add_argument('-a', '--pipeline_conf', type=str, nargs='+',
                        help='The name of configuration file which defines the pipeline configurations')
    parser.add_argument('-b', '--system_conf', type=str, nargs='+',
                        help='The name of configuration file which defines the system configurations')
    parser.add_argument('-c', '--freq', type=float, nargs='+',
                        help='The center frequency')
    parser.add_argument('-d', '--nchan', type=int, nargs='+',
                        help='The number of channels')
    parser.add_argument('-e', '--destination', type=str, nargs='+',
                        help='The destination')
    parser.add_argument('-f', '--part', type=int, nargs='+', # Count from zero
                        help='Which part of the capture for given beam')
    parser.add_argument('-g', '--hdr', type=int, nargs='+', # Count from zero
                        help='To capture packet header or not')
    parser.add_argument('-i', '--beam', type=int, nargs='+', # Count from zero
                        help='The beam number, counting from 0')
    
    args = parser.parse_args()
    main(args)