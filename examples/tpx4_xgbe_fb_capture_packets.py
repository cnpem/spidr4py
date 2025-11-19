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

#Import python native packages
import time
import threading
import queue
import numpy as np
import os
import h5py
import sys
import datetime
from argparse import ArgumentTypeError,BooleanOptionalAction #argparse is used inside helpers

import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.getcwd(),'..'))

#Import spidr4py packages
from spidr4 import rpc,utils, stream

#Import custom repository modules
import helpers
import fb_modules
from common import dacs

#Global shared variables and semaphore
current_frame = 0
lock = threading.Lock()

# -----------------------------------------------------------------------------------------------------------
#Create a dir_path to check if a dir exists
def dir_path(path):
    if os.path.isdir(path):
        return path
    else:
        raise ArgumentTypeError(f"readable_dir:{path} is not a valid path")

#Define function to plot images
def live_plot(line,img):
    line.set_data(img)
    line.set_clim(vmin=0, vmax=np.max(img))
    plt.pause(0.2)


#Define the asynchronous capture function to be launched as a thread
def async_capture(port,decoder,stop_event,new_frame_event):
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
        if decoder.decoded_packet.name == 'FRAME_START' and decoder.state != 'SEGMENT':
            global current_frame
            with lock:
                current_frame = decoder.frame_counter
            new_frame_event.set()
        if stop_event.is_set() and decoder.decoded_packet.name == 'FRAME_END' and decoder.state == 'IDLE':
            break

    # Stop and clean the current thread
    prt.stop()

# -----------------------------------------------------------------------------------------------------------
#Create argparse parameters
ns = helpers.cl_parse(with_chip_idx=True, args={
    "iface": dict(help="Network interface", type=str),
    "--xgbe-port": dict(help="10 GbE port", type=int, default=8192),
    '--path':dict(type=dir_path,required=True,help='path to output file'),
    '--filename':dict(type=str,default='decoded_frame',help='test name to be appended to output filename'),
    '--debug':dict(type=int,choices=range(4),default=1,help='Print debug level. 0: no print, 1: standard, 2: verbose, 3: all messages'),
    "--exposure-time-us": dict(type=int,default=10,help='Exposure time (shutter time) in microseconds'),
    '--th_e':dict(type=int,default=0,help='Threshold in e-'),
    '--auto-shutter':dict(action=BooleanOptionalAction,default=False,help='Retrigger shutter when readout finishes'),
    '--live-viewer':dict(action=BooleanOptionalAction,default=False,help='Open a simple live viewer to see current image. This can affects readout performance'),
})

# # Main loop, create network connection
with helpers.cl_connect() as channel:

    iface2find = ns.iface
    xgbe_port = ns.xgbe_port

    # Find network interface information
    # -----------------------------------------------------------------------------------------------------------
    # Get network card MAC address and IP address
    xgbe_host_mac, xgbe_host_ip = utils.get_nic_info(iface2find)

    # make-up an 10gbe IP for the spidr4 module, as long as it is not the same as xgbe_host_ip
    xgbe_spidr_ip = utils.inc_ip(xgbe_host_ip)

    # Get the services
    # ------------------------------------------------------------------------------------------------------
    ctrl = rpc.ControlInfoStub(channel)
    tpx4 = rpc.Timepix4Stub(channel)
    trigger = rpc.TriggerStub(channel)

    #Instantiate DAC class without initialzie DAC (do not override configuration)
    # ------------------------------------------------------------------------------------------------------
    dacs = dacs.DACs(tpx4,helpers.cl_chip_idx(),adc_half='TOP',adc='internal',debug=True, initialize=False)

    # Configure threshold in e. Polarity = 0 means electrons collection
    dacs.conf_threshold(THR_e=ns.th_e,debug=True)

    #Read if shutter control packets are enabled
    ans = tpx4.ReadReg(
            rpc.ReadRegRequest(
                idx=helpers.cl_chip_idx(),
                addr=0x4C02,
            ))
    shutter_control_packets = ((int.from_bytes(ans.data)&0x1) == 0x1)
    print(f'Shutter control packets are {'enabled' if shutter_control_packets else 'disabled'}')

    trigger.Enable(rpc.EMPTY)                       # Enable the trigger logic block
    trigger.StopAutoShutter(rpc.EMPTY)              # Just in case it was still running
    # Configure Trigger
    # ------------------------------------------------------------------------------------------------------
    trigger.SetConfig(
        rpc.TriggerConfig(
            shutter_input=rpc.SHUTTER_IN_AUTO_GEN,
            t0_input=rpc.T0SYNC_IN_SOFTWARE,
            #Works only with SHUTTER_IN_AUTO_GEN or SHUTTER_IN_AUTO_GEN_EXT_START
            auto_shutter_open_us=ns.exposure_time_us,
            auto_shutter_close_us=1,
            shutter_count=1,
            ####################################################################################
        )
    )
    trigger.ResetShutterCounter(rpc.EMPTY)          # Reset shutter counter

    if ns.live_viewer:
        img = np.zeros((512,448))
        fig = plt.figure()
        plt.ion()  # Turn interactive mode on
        # Plot the initial frame
        line = plt.imshow(img,origin='lower') # Note the comma to unpack the list returned by plt.plot
        cbar = plt.colorbar(line)

    # create class constructors to decode TOP and BOTTOM 64b packets
    decoder_top = fb_modules.Packet2Frame(debug=ns.debug,use_shutter_control_packets=shutter_control_packets)
    decoder_bot = fb_modules.Packet2Frame(debug=ns.debug,use_shutter_control_packets=shutter_control_packets)

    #Stop event is the signal to be sent to stop gracefully the threads
    stop_event = threading.Event()

    #Create two events to signalize frame starts and synchronize shutters
    start_event_top = threading.Event()
    start_event_bot = threading.Event()

    #Create and start top and bottom threads
    capture_thread_top = threading.Thread(target=async_capture, args=(xgbe_port,decoder_top,stop_event,start_event_top))
    capture_thread_bot = threading.Thread(target=async_capture, args=(xgbe_port+1,decoder_bot,stop_event,start_event_bot))
    capture_thread_top.start()
    capture_thread_bot.start()

    #Create an output log file
    output = {}

    #Create an argument array to save inside log file
    output['arguments'] = ''
    for arg in sys.argv:
        output['arguments'] += arg + ' '
    output['datetime'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    #Build the threshold
    output['threshold (e)'] = ns.th_e
    output['exposure time (us)'] = ns.exposure_time_us

    #control valid frames: used only for live viewer
    frame_to_plot = []

    #Wait exit, quit, q or e to send the stop event
    rec = ''
    status = trigger.GetStatus(rpc.EMPTY)           # get trigger status
    try:
        while rec not in ['exit','quit','e','q']:

            if ns.live_viewer and frame_to_plot:
                if frame_to_plot[0] < len(decoder_bot.frames):
                    idx = frame_to_plot.pop(0)
                    print(f'Plotting frame {idx}')
                    img = np.concatenate((decoder_bot.frames[idx], np.rot90(decoder_top.frames[idx], 2)), axis = 0)
                    live_plot(line,img)

            #auto shutter disabled waits for user to trigger next frame
            if ns.auto_shutter == False:
                rec = input('Type exit to stop reading threads and s to send a shutter....\n\r')
            #auto shutter enabled automatically retrigger the shutter
            else:
                rec = 'shutter'

            if rec in ['s','S','shutter']:

                #clear start flags
                start_event_top.clear()
                start_event_bot.clear()

                print(f'Sending shutter number {status.shutter_counter+1}')

                #wait start events to send a shutter during a valid frame
                start_event_top.wait()
                start_event_bot.wait()

                #send the shutter
                trigger.StartAutoShutter(rpc.EMPTY)             # Start auto-shutter

                if ns.live_viewer:
                    # Mark current frame as valid and trigger new plot
                    with lock:
                        frame_to_plot.append(current_frame + 1)

                status = trigger.GetStatus(rpc.EMPTY)           # get trigger status
                while status.auto_shutter_busy:
                    time.sleep(0.1)
                    status = trigger.GetStatus(rpc.EMPTY)       # Get the current status
    except KeyboardInterrupt:
        pass

    #Send signal to stop read threads after the current frame
    stop_event.set()

    status = trigger.GetStatus(rpc.EMPTY)           # get trigger status
    print(f"Shutter count: {status.shutter_counter}")

    plt.close()

    #wait threads to finish
    capture_thread_top.join()
    capture_thread_bot.join()

    # Concatenate botton and top matrixes to construct full images
    images = []
    for i in range(min(len(decoder_top.frames),len(decoder_bot.frames))):
        images.append(np.concatenate((decoder_bot.frames[i], np.rot90(decoder_top.frames[i], 2)), axis = 0))

    print(f'Saving output image: {os.path.join(ns.path,f'{ns.filename}.hdf5')}')
    # Save images in a .hdf5 file
    with h5py.File(os.path.join(ns.path,f'{ns.filename}.hdf5'), mode = 'w') as hdf5_file:
        hdf5_file.create_dataset('/entry/data/data', data = images)
        for key in output.keys():
            hdf5_file.attrs[key] = output[key]