#!/usr/bin/env python

# docker run --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all -e NVIDIA_DRIVER_CAPABILITIES=all --rm -it --ulimit memlock=40000000000 -v host_dir:doc_dir --net=host xinpingdeng/fold_mode
# docker run --runtime=nvidia tells the container that we will use nvidia/cuda library at runtime;
# --rm means the container will be released once it finishs;
# -i means it is a interactive container;
# -t oallocate a pseudo-TTY;
# as single character can be combined, we use -it instead of -i and -t here;
# --ulimit memlock=XX tell container to use XX bytes locked shared memory, NOTE, here is the size of shared memory used by all docker containers on host machine, not the current one;
# --net=host let container to use host network configuration;
# -e NVIDIA_DRIVER_CAPABILITIES controls which driver libraries/binaries will be mounted inside the container;
# -e NVIDIA_VISIBLE_DEVICES which GPUs will be made accessible inside the container;
# -v maps the host directory with the directory inside container, if the directories do not exist, docker will create them;
# Detail on how to setup nvidia docker image can be found at https://github.com/NVIDIA/nvidia-container-runtime;

import os, argparse

# ./do_launch.py -a 20 -b 0 -c 80000000000 -d /beegfs/DENG/docker -e /home/pulsar -f 50000 -g 50000 -i searchmode
# Read in command line arguments
parser = argparse.ArgumentParser(description='Launch the pipeline to catpure and fold data stream from BMF or from PSRDADA file')
parser.add_argument('-a', '--numa', type=int, nargs='+',
                    help='On which numa node we do the work, 0 or 1')
parser.add_argument('-b', '--ddir', type=str, nargs='+',
                    help='Directory with configuration file, timing model and to record data')
parser.add_argument('-c', '--hdir', type=str, nargs='+',
                    help='Home directory')
parser.add_argument('-d', '--uid', type=int, nargs='+',
                    help='UID of user')
parser.add_argument('-e', '--gid', type=int, nargs='+',
                    help='Group ID of the user belongs to')
parser.add_argument('-f', '--dname', type=str, nargs='+',
                    help='The name of docker container')

args    = parser.parse_args()
numa    = args.numa[0]    # It determines numa node id, memory allocation place, NiC id and also GPU id
ddir    = args.ddir[0]
hdir    = args.hdir[0]
uid     = args.uid[0]
gid     = args.gid[0]
dname   = args.dname[0]

gpu     = numa  # Either numa or "all"
dvolume = '{:s}:{:s}'.format(ddir, ddir)
hvolume = '{:s}:{:s}'.format(hdir, hdir)

com_line = "docker run --cap-add=SYS_PTRACE --security-opt seccomp=unconfined -it --rm --runtime=nvidia -e DISPLAY --net=host -v {:s} -v {:s} -v /tmp:/tmp -u {:d}:{:d} -e NVIDIA_VISIBLE_DEVICES={:s} -e NVIDIA_DRIVER_CAPABILITIES=all --cap-add=IPC_LOCK --ulimit memlock=-1:-1 --name {:s}{:d} xinpingdeng/{:s}".format(dvolume, hvolume, uid, gid, str(gpu), dname, numa, dname)

print com_line
print "\nYou are going to a docker container with the name {:s}{:d}!\n".format(dname, numa)

os.system(com_line)
