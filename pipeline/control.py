#!/usr/bin/env python

import socket
import os
import time
import parser
import argparse

# ./control.py -a 0 -b 0 -c START-OF-DATA:0:0
# ./control.py -a 0 -b 0 -c END-OF-DATA
# ./control.py -a 0 -b 0 -c STATUS-OF-TRAFFIC
# ./control.py -a 0 -b 0 -c END-OF-CAPTURE

parser = argparse.ArgumentParser(description='To control the capture')

parser.add_argument('-a', '--beam', type=int, nargs='+',
                    help='beam to control')
parser.add_argument('-b', '--part', type=int, nargs='+',
                    help='part to control')
parser.add_argument('-c', '--command', type=str, nargs='+',
                    help='command to send')

args    = parser.parse_args()
beam    = args.beam[0]
part    = args.part[0]
address = "/tmp/capture.beam{:d}.part{:d}".format(beam, part)
command = args.command[0]

start_buf = 0
start_byte = 48 * 7232 * 1000

sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
command_value = "{:s}:{:d}:{:d}".format(command, start_buf, start_byte)
print command_value
sock.sendto("{:s}\n".format(command_value), address)
sock.close()
