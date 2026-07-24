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
import sys
import datetime
from argparse import ArgumentTypeError,BooleanOptionalAction #argparse is used inside helpers
import subprocess

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
from common import hdf5

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
    line.set_clim(vmin=0, vmax=ns.scale if ns.scale != 0 else np.max(img))
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
    for data in stream.queue_generator(q, 60):
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
    '--path':dict(type=str,default='results',help='path to output files'),
    '--testname':dict(type=str,default='fb_acquisition',help='test name to create results directory'),
    '--debug':dict(type=int,choices=range(4),default=1,help='Print debug level. 0: no print, 1: standard, 2: verbose, 3: all messages'),
    "--exposure-time-us": dict(type=int,default=10,help='Exposure time (shutter time) in microseconds'),
    '--th':dict(type=int,default=None,help='Threshold in e- or dac_codes, see th-type argument'),
    "--th-type":dict(choices=['electrons','dac_code'],default='electrons',help='Define the type of the threshold set. Electrons or DAC codes'),
    '--scale':dict(type=int,default=0,required=False,help='Adjust maximum scale value in the live viewer plots. 0 means autoscale'),
    '--auto-shutter':dict(action=BooleanOptionalAction,default=False,help='Retrigger shutter when readout finishes'),
    '--live-viewer':dict(action=BooleanOptionalAction,default=False,help='Open a simple live viewer to see current image. This can affects readout performance'),
    '--save-crw-frames':dict(action=BooleanOptionalAction,default=False,help='Save CRW frames in the HDF5 file'),
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
    dacs = dacs.DACs(tpx4,helpers.cl_chip_idx(),adc_half='TOP',adc='internal',debug=True, load_dacs=False)

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

    #Create an image
    img = np.zeros((512,448),dtype=np.uint32)

    if ns.live_viewer:
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
    output['datetime'] = datetime.datetime.now().strftime("%Y-%m-%d_%Hh%Mm%Ss")

    #Get git repo information and append to metadata
    output['git url'] = subprocess.check_output('git config --get remote.origin.url',shell=True)
    output['git commit id'] = subprocess.check_output('git rev-parse HEAD',shell=True)
    output['git last commit date'] = subprocess.check_output("git log -1 --format='%cd'",shell=True)

    #Store all arguments to output as they will be saved as hdf5 attributes
    for arg_name, arg_value in vars(ns).items():
        output[arg_name] = arg_value

    #Create expected directories
    output['fullpath'] = os.path.join(os.getcwd(),ns.path,f'{output['datetime']}_{ns.testname}')
    os.makedirs(output['fullpath'],exist_ok=True)

    #Get Spidr4 and Timepix info
    # Get the version
    version = ctrl.GetVersion(rpc.EMPTY)
    output[version.product]=f"{version.majr}.{version.minr}.{version.patch} (git-info={version.commit_info})"

    fwversion = ctrl.GetFirmwareVersion(rpc.EMPTY)
    output[fwversion.product]=f"{fwversion.majr}.{fwversion.minr}.{fwversion.patch} (git-info={fwversion.commit_info})"

    serial = ctrl.GetSerial(rpc.EMPTY)
    output['SPIDR4 serial']=f"{serial.value:016x}"

    carrier = ctrl.GetChipBoardInfo(rpc.EMPTY)
    output['Chipboard Type'] = carrier.type
    output['Chipboard Serial'] = carrier.serial

    chips = ctrl.GetPixelChipInfo(rpc.EMPTY)
    if len(chips.items) > 1:
        print(f'ERROR: equalization script does not support boards with {len(chips.items)} chips')
        sys.exit(1)
    else:
        chip = chips.items[0]
        output['Chip Type'] = rpc.PixelChipType.Name(chip.type)
        output['Chip Revision'] = chip.revision
        output['Chip ID'] = f'{chip.chip_id:08x}'

    # Confgiure threshold if value different from None
    if ns.th != None:
        # Configure threshold depending on th_type
        if ns.th_type == 'electrons':
            output['Threshold Readback (e)'] = dacs.conf_threshold(THR_e=ns.th,debug=True)
        else:
            output['Threshold Readback (e)'] = dacs.conf_threshold_dac_code(dac_code=ns.th,debug=True)

    output['exposure time (us)'] = ns.exposure_time_us

    # Create the hdf5 output file
    out_hdf5 = hdf5.hdf5_nexus(os.path.join(output['fullpath'],'fb_acquisition.hdf5'),serial_number = ctrl.GetChipBoardInfo(rpc.EMPTY).serial)

    #Append metadata to output file
    out_hdf5.write_metadata(output)

    output_dacs = {}
    for dac in dacs.dacs.keys():
        output_dacs[f'{dac} readback (V)'] = dacs.dacs[dac]['readback']
        output_dacs[f'{dac} dac code'] = dacs.dacs[dac]['dac_code']
    out_hdf5.write_metadata(output_dacs)

    #Wait exit, quit, q or e to send the stop event
    rec = ''
    status = trigger.GetStatus(rpc.EMPTY)           # get trigger status

    try:
        while rec not in ['exit','quit','e','q']:

            #Update live viewer with last image
            if ns.live_viewer and status.shutter_counter > 0:
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

                #get shutter open frame index
                with lock:
                    shutter_open_frame = current_frame+1

                #Wait trigger
                status = trigger.GetStatus(rpc.EMPTY)           # get trigger status
                while status.auto_shutter_busy:
                    time.sleep(0.1)
                    status = trigger.GetStatus(rpc.EMPTY)       # Get the current status

                #get shutter close frame index
                with lock:
                    shutter_close_frame = current_frame+1

                #Wait for the current frame to finish and the next one
                for i in range(2):
                    #clear start flags to wait this frame end
                    start_event_top.clear()
                    start_event_bot.clear()

                    #wait until this frame ends
                    start_event_top.wait()
                    start_event_bot.wait()

                #Compute the image array
                img = np.sum(np.concatenate((decoder_bot.frames[shutter_open_frame:shutter_close_frame+1], np.rot90(decoder_top.frames[shutter_open_frame:shutter_close_frame+1], k = 2, axes=(1,2))), axis = 1),axis=0)

                #Append the image to the images array
                out_hdf5.append_image(img,field='data')

    except KeyboardInterrupt:
        pass

    #Send signal to stop read threads after the current frame
    stop_event.set()

    if ns.save_crw_frames == True:
        # Concatenate bottom and top matrixes to construct full images
        for idx in range(min(len(decoder_bot.frames),len(decoder_top.frames))):
            frame = np.concatenate((decoder_bot.frames[idx], np.rot90(decoder_top.frames[idx], 2)), axis = 0)
            out_hdf5.append_image(frame,field='CRWframes')

    status = trigger.GetStatus(rpc.EMPTY)           # get trigger status
    print(f"Finishing with {status.shutter_counter} shutters")

    plt.close()

    #wait threads to finish
    capture_thread_top.join()
    capture_thread_bot.join()

    # Close the file and end the script
    out_hdf5.close()
