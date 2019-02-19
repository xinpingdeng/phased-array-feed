#!/usr/bin/env python

import ConfigParser
import json
import numpy as np
import socket
import struct
import time
import shlex
from subprocess import PIPE, Popen, check_output
from inspect import currentframe, getframeinfo
import logging
import argparse
import threading
import inspect
import os

log = logging.getLogger("mpikat.paf_pipeline")

EXECUTE = True
#EXECUTE        = False

#NVPROF = True
NVPROF         = False

FILTERBANK_SOD = True   # Start filterbank data
# FILTERBANK_SOD  = False  # Do not start filterbank data

HEIMDALL = False   # To run heimdall on filterbank file or not
#HEIMDALL       = True   # To run heimdall on filterbank file or not

DBDISK = True   # To run dbdisk on filterbank file or not
#DBDISK         = False   # To run dbdisk on filterbank file or not

PAF_ROOT       = "/home/pulsar/xinping/phased-array-feed/"
DATA_ROOT      = "/beegfs/DENG/"
DADA_ROOT      = "{}/AUG/baseband/".format(DATA_ROOT)
SOURCE         = "J1819-1458"

PAF_CONFIG = {"instrument_name":    "PAF-BMF",
              "nchan_chk":    	     7,        # MHz
              "over_samp_rate":      (32.0/27.0),
              "prd":                 27,       # Seconds
              "df_res":              1.08E-4,  # Seconds
              "ndf_prd":             250000,

              "df_dtsz":      	     7168,
              "df_pktsz":     	     7232,
              "df_hdrsz":     	     64,

              "nbyte_baseband":      2,
              "npol_samp_baseband":  2,
              "ndim_pol_baseband":   2,

              "ncpu_numa":           10,  
              "mem_node":            60791751475, # has 10% spare
              "first_port":          17100,
              }

SEARCH_CONFIG_GENERAL = {"rbuf_baseband_ndf_chk":   16384,                 
                         "rbuf_baseband_nblk":      6,
                         "rbuf_baseband_nread":     1,                 
                         "tbuf_baseband_ndf_chk":   128,

                         "rbuf_filterbank_ndf_chk": 16384,
                         "rbuf_filterbank_nblk":    2,
                         "rbuf_filterbank_nread":   (HEIMDALL + DBDISK) if (HEIMDALL + DBDISK) else 1,

                         "nchan_filterbank":        512,
                         "cufft_nx":                128,

                         "nbyte_filterbank":        1,
                         "npol_samp_filterbank":    1,
                         "ndim_pol_filterbank":     1,

                         "ndf_stream":      	    1024,
                         "nstream":                 2,

                         "bind":                    1,

                         "pad":                     0,
                         "ndf_check_chk":           1024,

                         "detect_thresh":           10,
                         "dm":                      [1, 10000],
                         "zap_chans":               [],
                         }

SEARCH_CONFIG_1BEAM = {"dada_fname":             "{}/{}/{}_48chunks.dada".format(DADA_ROOT, SOURCE, SOURCE),
                       "rbuf_baseband_key":      ["dada"],
                       "rbuf_filterbank_key":    ["dade"],
                       "nchan_keep_band":        32768,
                       "nbeam":                  1,
                       "nport_beam":             3,
                       "nchk_port":              16,
}

SEARCH_CONFIG_2BEAMS = {"dada_fname":              "{}/{}/{}_33chunks.dada".format(DADA_ROOT, SOURCE, SOURCE),
                        "rbuf_baseband_key":       ["dada", "dadc"],
                        "rbuf_filterbank_key":     ["dade", "dadg"],
                        "nchan_keep_band":         24576,
                        "nbeam":                   2,
                        "nport_beam":              3,
                        "nchk_port":               11,
                        }

SPECTRAL_CONF_1BEAM = {"dada_fname":             "{}/{}/{}_48chunks.dada".format(DADA_ROOT, SOURCE, SOURCE),
                       "rbuf_baseband_key":      ["dada"],
                       "rbuf_filterbank_key":    ["dade"],
                       "nbeam":                  1,
                       "nport_beam":             3,
                       "nchk_port":              16,
}

SPECTRAL_CONFIG_2BEAMS = {"dada_fname":              "{}/{}/{}_33chunks.dada".format(DADA_ROOT, SOURCE, SOURCE),
                        "rbuf_baseband_key":       ["dada", "dadc"],
                        "rbuf_filterbank_key":     ["dade", "dadg"],
                        "nbeam":                   2,
                        "nport_beam":              3,
                        "nchk_port":               11,
                        }

class PipelineError(Exception):
    pass

PIPELINES = {}

def register_pipeline(name):
    def _register(cls):
        PIPELINES[name] = cls
        return cls
    return _register

class ExecuteCommand(object):
    def __init__(self, command):
        self._command = command
        self.stdout_callbacks = set()
        self.stderr_callbacks = set()
        self.returncode_callbacks = set()
        self._monitor_threads = []
        
        self._process = None
        self._executable_command = None
        self._stdout = None
        self._stderr = None
        self._returncode = None
        
        print self._command
        log.info(self._command)
        self._executable_command = shlex.split(self._command)
        log.info(self._executable_command)

        if EXECUTE:
            try:
                self._process = Popen(self._executable_command,
                                      stdout=PIPE,
                                      stderr=PIPE,
                                      bufsize=1,
                                      universal_newlines=True)
            except Exception as error:
                log.exception("Error while launching command: {} with error {}".format(self._command, error))
                self.returncode = self._command + "; RETURNCODE is: ' 1'"
            if self._process == None:
                self.returncode = self._command + "; RETURNCODE is: ' 1'"

            # Start monitors
            self._monitor_threads.append(threading.Thread(target=self._stdout_monitor))
            self._monitor_threads.append(threading.Thread(target=self._stderr_monitor))
            
            for thread in self._monitor_threads:
                thread.daemon = True
                thread.start()
                                    
    def __del__(self):
        class_name = self.__class__.__name__

    def finish(self):
        if EXECUTE:
            for thread in self._monitor_threads:
                thread.join()

    def stdout_notify(self):
        for callback in self.stdout_callbacks:
            callback(self._stdout, self)

    @property
    def stdout(self):
        return self._stdout

    @stdout.setter
    def stdout(self, value):
        self._stdout = value
        self.stdout_notify()

    def returncode_notify(self):
        for callback in self.returncode_callbacks:
            callback(self._returncode, self)

    @property
    def returncode(self):
        return self._returncode

    @returncode.setter
    def returncode(self, value):
        self._returncode = value
        self.returncode_notify()

    def stderr_notify(self):
        for callback in self.stderr_callbacks:
            callback(self._stderr, self)

    @property
    def stderr(self):
        return self._stderr

    @stderr.setter
    def stderr(self, value):
        self._stderr = value
        self.stderr_notify()

    
    def _stdout_monitor(self):
        if EXECUTE:
            while self._process.poll() == None:
                stdout = self._process.stdout.readline().rstrip("\n\r")
                if stdout != b"":
                    self.stdout = stdout
                #print self._command, "HERE STDOUT 1\n\n\n"
                
            if self._process.returncode and self._process.stderr.readline().rstrip("\n\r") == b"":
                self.returncode = self._command + "; RETURNCODE is: " + str(self._process.returncode)
            
    def _stderr_monitor(self):
        if EXECUTE:
            while self._process.poll() == None:
                stderr = self._process.stderr.readline().rstrip("\n\r")
                #print self._command, "HERE STDERR 1\n\n\n"
                if stderr != b"":
                    #print self._command, "HERE STDERR 2\n\n\n"
                    self.stderr = self._command + "; STDERR is: " + stderr
                    #print self._command, "HERE STDERR 3\n\n\n"
            
class Pipeline(object):
    def __init__(self):
        self._prd = PAF_CONFIG["prd"]
        self._first_port = PAF_CONFIG["first_port"]
        self._df_res = PAF_CONFIG["df_res"]
        self._df_dtsz = PAF_CONFIG["df_dtsz"]
        self._df_pktsz = PAF_CONFIG["df_pktsz"]
        self._df_hdrsz = PAF_CONFIG["df_hdrsz"]
        self._ncpu_numa = PAF_CONFIG["ncpu_numa"]
        self._nchan_chk = PAF_CONFIG["nchan_chk"]
        self._nbyte_baseband = PAF_CONFIG["nbyte_baseband"]
        self._ndim_pol_baseband = PAF_CONFIG["ndim_pol_baseband"]
        self._npol_samp_baseband = PAF_CONFIG["npol_samp_baseband"]
        self._mem_node           = PAF_CONFIG["mem_node"]
        self._execution_instances = []
        self._cleanup_commands = []
        
    def __del__(self):
        class_name = self.__class__.__name__

    def configure(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def deconfigure(self):
        raise NotImplementedError

    def _handle_execution_stdout(self, stdout, callback):
        if EXECUTE:
            print stdout

    def _handle_execution_returncode(self, returncode, callback):
        if EXECUTE:
            log.debug(returncode)
            if returncode:
                self.cleanup()
                raise PipelineError(returncode)

    def _handle_execution_stderr(self, stderr, callback):
        if EXECUTE:
            log.error(stderr)
            self.cleanup()
            raise PipelineError(stderr)

    def cleanup(self):
        # Kill existing process and free shared memory if there is any
        execution_instances = []
        for command in self._cleanup_commands:
            execution_instances.append(ExecuteCommand(command))            
        for execution_instance in execution_instances:         # Wait until the cleanup is done
            execution_instance.finish()
            
@register_pipeline("Search")
class Search(Pipeline):
    def __init__(self):
        super(Search, self).__init__()
        self._socket_address = []
        self._control_socket = []
        self._runtime_directory = []

        self._dbdisk_commands = []
        self._diskdb_commands = []
        self._heimdall_commands = []
        self._baseband2filterbank_commands = []
        self._baseband_create_buffer_commands = []
        self._baseband_delete_buffer_commands = []
        self._filterbank_create_buffer_commands = []
        self._filterbank_delete_buffer_commands = []

        self._dbdisk_execution_instances = []
        self._diskdb_execution_instances = []
        self._baseband2filterbank_execution_instances = []
        self._heimdall_execution_instances = []

        self._dm = SEARCH_CONFIG_GENERAL["dm"],
        self._pad = SEARCH_CONFIG_GENERAL["pad"]
        self._bind = SEARCH_CONFIG_GENERAL["bind"]
        self._nstream = SEARCH_CONFIG_GENERAL["nstream"]
        self._cufft_nx = SEARCH_CONFIG_GENERAL["cufft_nx"]
        self._zap_chans = SEARCH_CONFIG_GENERAL["zap_chans"]
        self._ndf_stream = SEARCH_CONFIG_GENERAL["ndf_stream"]
        self._detect_thresh = SEARCH_CONFIG_GENERAL["detect_thresh"]
        self._ndf_check_chk = SEARCH_CONFIG_GENERAL["ndf_check_chk"]
        self._nchan_filterbank = SEARCH_CONFIG_GENERAL["nchan_filterbank"]
        self._nbyte_filterbank = SEARCH_CONFIG_GENERAL["nbyte_filterbank"]
        self._rbuf_baseband_nblk = SEARCH_CONFIG_GENERAL["rbuf_baseband_nblk"]
        self._ndim_pol_filterbank = SEARCH_CONFIG_GENERAL["ndim_pol_filterbank"]
        self._rbuf_baseband_nread = SEARCH_CONFIG_GENERAL["rbuf_baseband_nread"]
        self._npol_samp_filterbank = SEARCH_CONFIG_GENERAL["npol_samp_filterbank"]
        self._rbuf_filterbank_nblk = SEARCH_CONFIG_GENERAL["rbuf_filterbank_nblk"]
        self._rbuf_baseband_ndf_chk = SEARCH_CONFIG_GENERAL["rbuf_baseband_ndf_chk"]
        self._rbuf_filterbank_nread = SEARCH_CONFIG_GENERAL["rbuf_filterbank_nread"]
        self._tbuf_baseband_ndf_chk = SEARCH_CONFIG_GENERAL["tbuf_baseband_ndf_chk"]
        self._rbuf_filterbank_ndf_chk = SEARCH_CONFIG_GENERAL["rbuf_filterbank_ndf_chk"]

        self._cleanup_commands = ["pkill -9 -f dada_diskdb",
                                  "pkill -9 -f baseband2filter", # process name, maximum 16 bytes (15 bytes visiable)
                                  "pkill -9 -f heimdall",
                                  "pkill -9 -f dada_dbdisk",
                                  "ipcrm -a"]

    def configure(self, ip, pipeline_config):
        # Setup parameters of the pipeline
        self._ip = ip
        self._pipeline_config = pipeline_config
        self._numa = int(ip.split(".")[3]) - 1
        self._server = int(ip.split(".")[2])
        
        self._nbeam = self._pipeline_config["nbeam"]
        self._nchk_port = self._pipeline_config["nchk_port"]
        self._dada_fname = self._pipeline_config["dada_fname"]
        self._nport_beam = self._pipeline_config["nport_beam"]
        self._nchan_keep_band = self._pipeline_config["nchan_keep_band"]
        self._rbuf_baseband_key = self._pipeline_config["rbuf_baseband_key"]
        self._rbuf_filterbank_key = self._pipeline_config["rbuf_filterbank_key"]
        self._blk_res = self._df_res * self._rbuf_baseband_ndf_chk
        self._nchk_beam = self._nchk_port * self._nport_beam
        self._nchan_baseband = self._nchan_chk * self._nchk_beam
        self._ncpu_pipeline = self._ncpu_numa / self._nbeam
        self._rbuf_baseband_blksz = self._nchk_port * \
            self._nport_beam * self._df_dtsz * self._rbuf_baseband_ndf_chk
        self._rbuf_filterbank_blksz = int(self._nchan_filterbank * self._rbuf_baseband_blksz *
                                          self._nbyte_filterbank * self._npol_samp_filterbank *
                                          self._ndim_pol_filterbank / float(self._nbyte_baseband *
                                                                            self._npol_samp_baseband *
                                                                            self._ndim_pol_baseband *
                                                                            self._nchan_baseband *
                                                                            self._cufft_nx))
        
        # To see if we can process baseband data with integer repeats
        if self._rbuf_baseband_ndf_chk % (self._ndf_stream * self._nstream):
            self.cleanup()
            raise PipelineError("data in baseband ring buffer block can only "
                                "be processed by baseband2filterbank with integer repeats")

        # To see if we have enough memory
        if self._nbeam*(self._rbuf_filterbank_blksz + self._rbuf_baseband_blksz) > self._mem_node:
            self.cleanup()
            raise PipelineError("We do not have enough shared memory for the setup "
                                "Try to reduce the ring buffer block number "
                                "or reduce the number of packets in each ring buffer block")
        
        # To be safe, kill all related softwares and free shared memory
        self.cleanup()
                
        # To setup commands for each process
        baseband2filterbank = "{}/src/baseband2filterbank_main".format(PAF_ROOT)
        if not os.path.isfile(baseband2filterbank):
            self.cleanup()
            raise PipelineError("{} is not exist".format(baseband2filterbank))
        if not os.path.isfile(self._dada_fname):
            self.cleanup()
            raise PipelineError("{} is not exist".format(self._dada_fname))                
        for i in range(self._nbeam):      
            if EXECUTE:
                # To get directory for runtime information
                runtime_directory = "{}/pacifix{}_numa{}_process{}".format(DATA_ROOT, self._server, self._numa, i)
                if not os.path.isdir(runtime_directory):
                    try:
                        os.makedirs(directory)
                    except:
                        self.cleanup()
                        raise PipelineError("Fail to create {}".format(runtime_directory))
            else:
                runtime_directory = None                
            self._runtime_directory.append(runtime_directory)

            # diskdb command
            diskdb_cpu = self._numa * self._ncpu_numa + i * self._ncpu_pipeline                                      
            self._diskdb_commands.append("taskset -c {} dada_diskdb -k {:s} -f {:s} -o {:d} -s".format(diskdb_cpu, self._rbuf_baseband_key[i], self._dada_fname, 0))

            # baseband2filterbank command
            baseband2filterbank_cpu = self._numa * self._ncpu_numa + i * self._ncpu_pipeline + 1
            command = "taskset -c {} ".format(baseband2filterbank_cpu)
            if NVPROF:
                command += "nvprof "
            command += ("{} -a {} -b {} -c {} -d {} -e {} "
                        "-f {} -i {} -j {} -k {} -l {} ").format(baseband2filterbank, self._rbuf_baseband_key[i], self._rbuf_filterbank_key[i],
                                                                 self._rbuf_filterbank_ndf_chk, self._nstream, self._ndf_stream,
                                                                 self._runtime_directory[i], self._nchk_beam, self._cufft_nx,
                                                                 self._nchan_filterbank, self._nchan_keep_band)
            #command += ("{} -a {} -b {} -c {} -d {} -e {} "
            #            "-f {} -i {} -j {} ").format(baseband2filterbank, self._rbuf_baseband_key[i], self._rbuf_filterbank_key[i],
            #                                         self._rbuf_filterbank_ndf_chk, self._nstream, self._ndf_stream,
            #                                         self._runtime_directory[i], self._nchk_beam, self._cufft_nx)
            if FILTERBANK_SOD:
                command += "-g 1"
            else:
                command += "-g 0"
            self._baseband2filterbank_commands.append(command)

            # Command to create filterbank ring buffer
            dadadb_cpu = self._numa * self._ncpu_numa + i * self._ncpu_pipeline + 2
            self._filterbank_create_buffer_commands.append(("taskset -c {} dada_db -l -p -k {:} "
                                                            "-b {:} -n {:} -r {:}").format(dadadb_cpu, self._rbuf_filterbank_key[i],
                                                                                           self._rbuf_filterbank_blksz,
                                                                                           self._rbuf_filterbank_nblk,
                                                                                           self._rbuf_filterbank_nread))

            # command to create baseband ring buffer
            self._baseband_create_buffer_commands.append(("taskset -c {} dada_db -l -p -k {:} "
                                                          "-b {:} -n {:} -r {:}").format(dadadb_cpu, self._rbuf_baseband_key[i],
                                                                                         self._rbuf_baseband_blksz,
                                                                                         self._rbuf_baseband_nblk,
                                                                                         self._rbuf_baseband_nread))

            # command to delete filterbank ring buffer
            self._filterbank_delete_buffer_commands.append(
                "taskset -c {} dada_db -d -k {:}".format(dadadb_cpu, self._rbuf_filterbank_key[i]))

            # command to delete baseband ring buffer
            self._baseband_delete_buffer_commands.append(
                "taskset -c {} dada_db -d -k {:}".format(dadadb_cpu, self._rbuf_baseband_key[i]))

            # Command to run heimdall
            heimdall_cpu = self._numa * self._ncpu_numa + i * self._ncpu_pipeline + 3
            command = "taskset -c {} ".format(heimdall_cpu)
            if NVPROF:
                command += "nvprof "
            command += ("heimdall -k {} -detect_thresh {} -output_dir {} ").format(self._rbuf_filterbank_key[i],
                                                                                   self._detect_thresh, runtime_directory)
            if self._zap_chans:
                zap = ""
                for zap_chan in self._zap_chans:
                    zap += " -zap_chans {} {}".format(
                        self._zap_chan[0], self._zap_chan[1])
                command += zap
                if self._dm:
                    command += "-dm {} {}".format(self._dm[0], self._dm[1])
            self._heimdall_commands.append(command)

            # Command to run dbdisk
            dbdisk_cpu = self._numa * self._ncpu_numa + i * self._ncpu_pipeline + 4
            command = "dada_dbdisk -b {} -k {} -D {} -o -s -z".format(
                dbdisk_cpu, self._rbuf_filterbank_key[i], self._runtime_directory[i])
            self._dbdisk_commands.append(command)

    def start(self):
        # Create baseband ring buffer
        execution_instances = []
        for command in self._baseband_create_buffer_commands:
            execution_instances.append(ExecuteCommand(command))
        for execution_instance in execution_instances:
            execution_instance.finish()

        # Create ring buffer for filterbank data
        execution_instances = []
        for command in self._filterbank_create_buffer_commands:
            execution_instances.append(ExecuteCommand(command))
        for execution_instance in execution_instances:         # Wait until the buffer creation is done
            execution_instance.finish()

        # Execute the diskdb
        self._diskdb_execution_instances = []
        for command in self._diskdb_commands:
            execution_instance = ExecuteCommand(command)
            #self._execution_instances.append(execution_instance)
            execution_instance.stdout_callbacks.add(self._handle_execution_stdout)
            self._dbdisk_execution_instances.append(execution_instance)

        # Run baseband2filterbank
        self._baseband2filterbank_execution_instances = []
        for command in self._baseband2filterbank_commands:
            execution_instance = ExecuteCommand(command)
            self._execution_instances.append(execution_instance)
            if not NVPROF:  # Do not check stderr or returncode if there is any third party software
                execution_instance.stderr_callbacks.add(self._handle_execution_stderr)
                #execution_instance.returncode_callbacks.add(self._handle_execution_returncode)
            execution_instance.stdout_callbacks.add(self._handle_execution_stdout)
            self._baseband2filterbank_execution_instances.append(execution_instance)

        if HEIMDALL:  # run heimdall if required
            self._heimdall_execution_instances = []
            for command in self._heimdall_commands:
                execution_instance = ExecuteCommand(command)
                self._execution_instances.append(execution_instance)
                execution_instance.returncode_callbacks.add(
                    self._handle_execution_returncode)
                execution_instance.stdout_callbacks.add(self._handle_execution_stdout)
                self._heimdall_execution_instances.append(execution_instance)
                
        if DBDISK:   # Run dbdisk if required
            self._dbdisk_execution_instances = []
            for command in self._dbdisk_commands:
                execution_instance = ExecuteCommand(command)
                self._execution_instances.append(execution_instance)
                execution_instance.stdout_callbacks.add(self._handle_execution_stdout)
                execution_instance.returncode_callbacks.add(
                    self._handle_execution_returncode)
                self._dbdisk_execution_instances.append(execution_instance)

    def stop(self):
        if DBDISK:
            for execution_instance in self._dbdisk_execution_instances:
                execution_instance.finish()
        if HEIMDALL:
            for execution_instance in self._heimdall_execution_instances:
                execution_instance.finish()
                
        for execution_instance in self._baseband2filterbank_execution_instances:
            execution_instance.finish()

        for execution_instance in self._diskdb_execution_instances:
            execution_instance.finish()
            
        # To delete filterbank ring buffer
        execution_instances = []
        for command in self._filterbank_delete_buffer_commands:
            execution_instances.append(ExecuteCommand(command))
        for execution_instance in execution_instances:
            execution_instance.finish()
        
        # To delete baseband ring buffer
        execution_instances = []
        for command in self._baseband_delete_buffer_commands:
            execution_instances.append(ExecuteCommand(command))
        for execution_instance in execution_instances:
            execution_instance.finish()
            
    def deconfigure(self):
        pass
        
@register_pipeline("Search2Beams")
class Search2Beams(Search):

    def __init__(self):
        super(Search2Beams, self).__init__()

    def configure(self, ip):
        super(Search2Beams, self).configure(ip, SEARCH_CONFIG_2BEAMS)

    def start(self):
        super(Search2Beams, self).start()

    def stop(self):
        super(Search2Beams, self).stop()

    def deconfigure(self):
        super(Search2Beams, self).deconfigure()


@register_pipeline("Search1Beam")
class Search1Beam(Search):

    def __init__(self):
        super(Search1Beam, self).__init__()

    def configure(self, ip):
        super(Search1Beam, self).configure(ip, SEARCH_CONFIG_1BEAM)

    def start(self):
        super(Search1Beam, self).start()

    def stop(self):
        super(Search1Beam, self).stop()

    def deconfigure(self):
        super(Search1Beam, self).deconfigure()

if __name__ == "__main__":
    host_id = check_output("hostname").strip()[-1]

    parser = argparse.ArgumentParser(
        description='To run the pipeline for my test')
    parser.add_argument('-a', '--numa', type=int, nargs='+',
                        help='The ID of numa node')
    parser.add_argument('-b', '--beam', type=int, nargs='+',
                        help='The number of beams')

    args = parser.parse_args()
    numa = args.numa[0]
    beam = args.beam[0]
    ip = "10.17.{}.{}".format(host_id, numa + 1)

    if beam == 1:
        freq = 1340.5
    if beam == 2:
        freq = 1337.0
        
    for i in range(1):    
        print "\nCreate pipeline ...\n"
        if beam == 1:
            search_mode = Search1Beam()
        if beam == 2:
            search_mode = Search2Beams()
        
        print "\nConfigure it ...\n"
        search_mode.configure(ip)

        for j in range(1):
            print "\nStart it ...\n"
            search_mode.start()
            #print "\nStop it ...\n"
            #search_mode.stop()
        
        #print "\nDeconfigure it ...\n"
        #search_mode.deconfigure()
