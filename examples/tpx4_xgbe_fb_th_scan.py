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
import matplotlib.pyplot as plt
from argparse import ArgumentTypeError #argparse is used inside helpers

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

#create a default encoer to save JSON from numpy types
#JSON dumps need to encode numpy objects
def numpy_encoder(obj):
    if type(obj).__module__ == np.__name__:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return obj.item()
    raise TypeError('Unknown type:', type(obj))

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
    for data in stream.queue_generator(q, 20):
        decoder.read_packet(data)
        #Stop thread when stop event is set and the current frame is finished
        if decoder.decoded_packet.name == 'FRAME_START' and decoder.state == 'FRAME':
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
    '--path':dict(type=dir_path,required=True,help='path to output files'),
    '--filename':dict(type=str,default='th_scan',help='test name to be appended to output filename'),
    '--debug':dict(type=int,choices=range(4),default=1,help='Print debug level. 0: no print, 1: standard, 2: verbose, 3: all messages'),
    "--exposure-time-us": dict(type=int,default=10,help='Exposure time (shutter time) in microseconds'),
    '--th_low_e':dict(type=int,default=0,help='Threshold low in e-'),
    '--th_high_e':dict(type=int,required=True,help='Threshold high in e-'),
    '--n_points':dict(required=True,type=int,default=1,help='Number of threshold samples'),
    '--repeat':dict(required=False,type=int,default=1,help='Number of repetitions per threshold sample')

})

TH_STEP_MAX = 80
th_step = (ns.th_high_e - ns.th_low_e)/(ns.n_points-1)
if th_step < TH_STEP_MAX:
    print(f'WARNING: Threshold step is {th_step:.2f} electrons. Please consider to proceed with a step larger than {TH_STEP_MAX} electrons.')
    res = input('Do you wish to continue? (y or n)\n\r')
    if res in ['y','Y','Yes','yes']:
        pass
    else:
        sys.exit(1)

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
    output['exposure time (us)'] = ns.exposure_time_us
    output['n points'] = ns.n_points
    output['repeat'] = ns.repeat
    output['threshold low (e)'] = ns.th_low_e
    output['threshold high (e)'] = ns.th_high_e

    #Create output data dictionary
    output_data = {}

    #Build the threshold array to iterate
    output_data['threshold_target'] = np.linspace(ns.th_low_e,ns.th_high_e,ns.n_points)
    valid_frames = []

    output_data['threshold_readback'] = []

    for index,th in enumerate(output_data['threshold_target']):
        # Configure threshold in e. Polarity = 0 means electrons collection
        print('-----------------------------------------------------------')
        output_data['threshold_readback'].append(dacs.conf_threshold(THR_e=th,force_FBK=False,debug=True))

        for i in range(ns.repeat):

            print(f'Threshold scan step {index+1}/{ns.n_points}: th target {th:.2f} e-. Measured {output_data['threshold_readback'][index]:.2f}. Repetition {i+1}/{ns.repeat}')

            #clear start flags
            start_event_top.clear()
            start_event_bot.clear()

            #wait start events to send a shutter during a valid frame
            start_event_top.wait()
            start_event_bot.wait()

            with lock:
                valid_frames.append(current_frame+1)

            #send the shutter
            trigger.StartAutoShutter(rpc.EMPTY)             # Start auto-shutter
            status = trigger.GetStatus(rpc.EMPTY)           # get trigger status
            while status.auto_shutter_busy:
                time.sleep(0.1)
                status = trigger.GetStatus(rpc.EMPTY)       # Get the current status

    #clear start flags
    start_event_top.clear()
    start_event_bot.clear()
    #wait the current frame (last shutter) to finish
    start_event_top.wait()
    start_event_bot.wait()
    #Send signal to stop read threads after the current frame
    stop_event.set()

    status = trigger.GetStatus(rpc.EMPTY)           # get trigger status
    print(f"Shutter total count: {status.shutter_counter}")

    print(f'Valid frames: {valid_frames}')

    #wait threads to finish
    capture_thread_top.join()
    capture_thread_bot.join()

    # Concatenate botton and top matrixes to construct full images, considering valid frames
    images = []
    for i in valid_frames:
        images.append(np.concatenate((decoder_bot.frames[i], np.rot90(decoder_top.frames[i], 2)), axis = 0))

    #Sum the counts of valid images
    counter_sum = np.sum(images,axis=(1,2))
    counter_max = np.max(images,axis=(1,2))
    counter_mean = np.mean(images,axis=(1,2))
    output_data['sum_per_image'] = counter_sum

    #Calculated the mean for repeated images
    output_data['sum_per_threshold'] = []
    output_data['max_per_threshold'] = []
    output_data['mean_per_threshold'] = []
    for i in range(ns.n_points):
        output_data['sum_per_threshold'].append(np.sum(counter_sum[i*ns.repeat:(i+1)*ns.repeat])/ns.repeat)
        output_data['max_per_threshold'].append(np.max(counter_max[i*ns.repeat:(i+1)*ns.repeat]))
        output_data['mean_per_threshold'].append(np.mean(counter_mean[i*ns.repeat:(i+1)*ns.repeat]))

    print(f'Saving output image: {os.path.join(ns.path,f'{ns.filename}.hdf5')}')
    # Save images in a .hdf5 file
    with h5py.File(os.path.join(ns.path,f'{ns.filename}.hdf5'), mode = 'w') as hdf5_file:
        hdf5_file.create_dataset('/entry/data/data', data = images)
        for key in output.keys():
            hdf5_file.attrs[key] = output[key]
        for key in output_data.keys():
            hdf5_file.create_dataset(f'/entry/data/{key}', data = output_data[key])

    #Plot the figure
    plt.figure()
    plt.plot(output_data['threshold_target'],output_data['sum_per_threshold'])
    plt.title(f'Threshold Scan - {ns.exposure_time_us} us exposure')
    plt.xlabel('Threshold (e)')
    plt.ylabel('Counts Sum')
    plt.grid()
    plt.tight_layout()
    plt.savefig(os.path.join(ns.path,f'{ns.filename}.png'))
    plt.show()