#!/usr/bin/env python3

#############################################################################################################
#
#  tpx4_xgbe_fb_th_scan.py
#  
#  Performs frame-based threshold scan using 10G interface.
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
from argparse import ArgumentTypeError #argparse is used inside helpers

sys.path.insert(0, os.path.join(os.getcwd(),'..'))

#Import spidr4py packages
from spidr4 import rpc,utils,stream,tpx4tools

#Import custom repository modules
import helpers
import fb_modules
from common import dacs

# -----------------------------------------------------------------------------------------------------------
#Create a dir_path to check if a dir exists
def dir_path(path):
    if os.path.isdir(path):
        return path
    else:
        raise ArgumentTypeError(f"readable_dir:{path} is not a valid path")

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
        if decoder.decoded_packet.name == 'FRAME_START' and decoder.state == 'FRAME':
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
    '--path':dict(type=dir_path,required=True,help='path to output files'),
    '--filename':dict(type=str,default='testpulse',help='test name to be appended to output filename'),
    '--debug':dict(type=int,choices=range(4),default=1,help='Print debug level. 0: no print, 1: standard, 2: verbose, 3: all messages'),
    '--th_e':dict(type=int,default=3000,help='Threshold low in e-'),
    '--n_pulses':dict(required=True,type=int,default=1,help='Number of pulses of testpulse'),
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
    tpx4 = rpc.Timepix4Stub(channel)

    #Instantiate DAC class without initialzie DAC (do not override configuration)
    # ------------------------------------------------------------------------------------------------------
    dacs = dacs.DACs(tpx4,helpers.cl_chip_idx(),adc_half='TOP',adc='internal',debug=True, initialize=False)
    dacs.conf_threshold(THR_e=ns.th_e)

    #Read if shutter control packets are enabled
    ans = tpx4.ReadReg(
            rpc.ReadRegRequest(
                idx=helpers.cl_chip_idx(),
                addr=0x4C02,
            ))
    shutter_control_packets = ((int.from_bytes(ans.data)&0x1) == 0x1)
    print(f'Shutter control packets are {'enabled' if shutter_control_packets else 'disabled'}')

    # Configure Test Pulse
    # ------------------------------------------------------------------------------------------------------
    # Read Timepix4 configuration
    pixelConfigBlob = tpx4.ConfigGetPixels(
        rpc.ChipIndex(idx=helpers.cl_chip_idx())
    ).config

    # Convert it to x,y
    pixelConfig = tpx4tools.chip2logic_cfg_matrix(
        np.frombuffer(pixelConfigBlob, dtype=np.uint8)
    )

    #update test pulse for selected pixels
    img = helpers.get_test_image()
    for X in range(0,448,1):
        for Y in range(0,512,1):
            if img[Y,X]:
                pixelConfig[Y][X] |= (0x1<<6)
                #print(f'Pixel X:{X:03d} Y:{Y:03d} Equal: 0x{equal[X][Y]:02X} or {equal[X][Y]:02d} Mask: {mask[X][Y]}. Pixel cfg: 0x{pixel_cfg_mtx[Y][X]:02X} or {pixel_cfg_mtx[Y][X]:02d}')

    #Serialize pixel config data
    config_blob = tpx4tools.logic2chip_cfg_matrix(pixelConfig)

    #Send pixel configuration to the ASIC
    tpx4.ConfigPixels(
            rpc.Tpx4PixelConfig(
                    idx=helpers.cl_chip_idx(),
                    config=config_blob.tobytes()
            )
    )

    # Enable the test-pulse
    # ------------------------------------------------------------------------------------------------------
    tpx4.TestPulseEnable(rpc.ChipIndex(idx=helpers.cl_chip_idx()))

    # Frame decoder strucutre and readout threads
    # ------------------------------------------------------------------------------------------------------
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
    output['threshold'] = ns.th_e
    output['n_pulses'] = ns.n_pulses

    #clear start flags
    start_event_top.clear()
    start_event_bot.clear()

    #wait start events to send a shutter during a valid frame
    start_event_top.wait()
    start_event_bot.wait()

    t0 = time.time()

    # Start the test pulse
    # Scan through all columns of the chip
    # ------------------------------------------------------------------------------------------------------
    helpers.scan_tp(tpx4, helpers.cl_chip_idx(),n_pulses=ns.n_pulses)

    t_elapsed = (time.time() - t0)
    print(f'Elapsed time for test pulse scanning: {t_elapsed} seconds')

    #clear start flags
    start_event_top.clear()
    start_event_bot.clear()
    #wait the current frame (last shutter) to finish
    start_event_top.wait()
    start_event_bot.wait()
    #Send signal to stop read threads after the current frame
    stop_event.set()

    #wait threads to finish
    capture_thread_top.join()
    capture_thread_bot.join()

    # Concatenate botton and top matrixes to construct full images, considering valid frames
    images = []
    for i in range(min(len(decoder_top.frames),len(decoder_bot.frames))):
        images.append(np.concatenate((decoder_bot.frames[i], np.rot90(decoder_top.frames[i], 2)), axis = 0))

    print(f'Saving output image: {os.path.join(ns.path,f'{ns.filename}.hdf5')}')
    # Save images in a .hdf5 file
    with h5py.File(os.path.join(ns.path,f'{ns.filename}.hdf5'), mode = 'w') as hdf5_file:
        hdf5_file.create_dataset('/entry/data/data', data = images)
        for key in output.keys():
            hdf5_file.attrs[key] = output[key]

    # Reset Test Pulse Bit
    # ------------------------------------------------------------------------------------------------------
    # Read Timepix4 configuration
    pixelConfigBlob = tpx4.ConfigGetPixels(
        rpc.ChipIndex(idx=helpers.cl_chip_idx())
    ).config

    # Convert it to x,y
    pixelConfig = tpx4tools.chip2logic_cfg_matrix(
        np.frombuffer(pixelConfigBlob, dtype=np.uint8)
    )

    #reset test pulse for all pixels
    for X in range(0,448,1):
        for Y in range(0,512,1):
            if img[Y,X]:
                pixelConfig[Y][X] &= (0b10111111)

    #Serialize pixel config data
    config_blob = tpx4tools.logic2chip_cfg_matrix(pixelConfig)

    #Send pixel configuration to the ASIC
    tpx4.ConfigPixels(
            rpc.Tpx4PixelConfig(
                    idx=helpers.cl_chip_idx(),
                    config=config_blob.tobytes()
            )
    )