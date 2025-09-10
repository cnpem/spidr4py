#!/usr/bin/env python3

#############################################################################################################
#
#  tpx4_xgbe_fb_capture_packets.py
#  
#  Performs frame-based acquisitions using 10G interface and build an HDF5 file. This script
#    is an alternative to SDAQ   
#
#  Authors: 
#   Mauricio Donatti <mauricio.donatti@lnls.br>
#
#  September 2025
#
#############################################################################################################

#Import spidr4py packages
from spidr4 import utils, stream

#Import custom repository modules
import helpers
import fb_modules

#Import python native packages
import threading
import queue
import numpy as np
import os
import h5py
from argparse import ArgumentTypeError,BooleanOptionalAction #argparse is used inside helpers

# -----------------------------------------------------------------------------------------------------------
#Create a dir_path to check if a dir exists
def dir_path(path):
    if os.path.isdir(path):
        return path
    else:
        raise ArgumentTypeError(f"readable_dir:{path} is not a valid path")

#Define the asynchronous capture function to be launched as a thread
def async_capture(port,decoder,stop_event):
    # Configure local data acquisition
    # ------------------------------------------------------------------------------------------------------
    print(f'Starting async capture. Port {port}')
    q = queue.Queue()

    # Create a thread to readout the current link
    prt = stream.udp_read_thread(xgbe_host_ip, port, q)

    # Read-data and put in matrix
    # ------------------------------------------------------------------------------------------------------
    for data in stream.queue_generator(q, 20):
        decoder.read_packet(data)
        #Stop thread when stop event is set and the current frame is finished
        if stop_event.is_set() and decoder.decoded_packet.name == 'FRAME_END':
            break

    # Stop and clean the current thread
    prt.stop()

# -----------------------------------------------------------------------------------------------------------
#Create argparse parameters
ns = helpers.cl_parse(with_chip_idx=True, args={
    "iface": dict(help="Network interface", type=str),
    "--xgbe-port": dict(help="10 GbE port", type=int, default=8192),
    '--path':dict(type=dir_path,required=True,help='path to output file'),
    '--shutter-control-packets':dict(action=BooleanOptionalAction,default=False,help='use shutter rise/fall to compose valid frames'),
    '--filename':dict(type=str,default='decoded_frame',help='test name to be appended to output filename'),
    '--debug':dict(type=int,choices=range(4),default=1,help='Print debug level. 0: no print, 1: standard, 2: verbose, 3: all messages'),
})

iface2find = ns.iface
xgbe_port = ns.xgbe_port

# Find network interface information
# -----------------------------------------------------------------------------------------------------------
# Get network card MAC address and IP address
xgbe_host_mac, xgbe_host_ip = utils.get_nic_info(iface2find)

# make-up an 10gbe IP for the spidr4 module, as long as it is not the same as xgbe_host_ip
xgbe_spidr_ip = utils.inc_ip(xgbe_host_ip)

# create class constructors to decode TOP and BOTTOM 64b packets
decoder_top = fb_modules.Packet2Frame(debug=ns.debug,use_shutter_control_packets=ns.shutter_control_packets) 
decoder_bot = fb_modules.Packet2Frame(debug=ns.debug,use_shutter_control_packets=ns.shutter_control_packets) 

#Stop event is the signal to be sent to stop gracefully the threads
stop_event = threading.Event()

#Create and start top and bottom threads
capture_thread_top = threading.Thread(target=async_capture, args=(xgbe_port,decoder_top,stop_event))
capture_thread_bot = threading.Thread(target=async_capture, args=(xgbe_port+1,decoder_bot,stop_event))
capture_thread_top.start()
capture_thread_bot.start()

#Wait exit, quit, q or e to send the stop event
rec = ''
while rec not in ['exit','quit','e','q']:
    rec = input('Type exit to stop reading threads....\n\r')

#Send signal to stop read threads after the current frame
stop_event.set()

#wait threads to finish
capture_thread_top.join()
capture_thread_bot.join()

# Concatenate botton and top matrixes to construct full images
images = []
for i in range(min(len(decoder_top.frames),len(decoder_bot.frames))):
    images.append(np.concatenate((decoder_bot.frames[i], np.rot90(decoder_top.frames[i], 2)), axis = 0))

print(f'Saving output image image in {ns.path} as {ns.filename}')
# Save images in a .hdf5 file
with h5py.File(os.path.join(ns.path,f'{ns.filename}.hdf5'), mode = 'w') as hdf5_file:
    hdf5_file.create_dataset('/entry/data/data', data = images)