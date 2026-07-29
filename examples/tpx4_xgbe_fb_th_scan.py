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
import sys
import datetime
import matplotlib.pyplot as plt
from argparse import ArgumentTypeError,BooleanOptionalAction #argparse is used inside helpers
import subprocess

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
    for data in stream.queue_generator(q, 60):
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

def int_greater_1(x):
    x = int(x) # Convert to int
    if x < 2:
        raise ArgumentTypeError(f"{x} must be an integer >= 2")
    return x

# -----------------------------------------------------------------------------------------------------------
#Create argparse parameters
ns = helpers.cl_parse(with_chip_idx=True, args={
    "iface": dict(help="Network interface", type=str),
    "--xgbe-port": dict(help="10 GbE port", type=int, default=8192),
    '--path':dict(type=dir_path,default='results',help='path to output files'),
    '--testname':dict(type=str,default='th-scan',help='test name to be create results dir'),
    '--debug':dict(type=int,choices=range(4),default=1,help='Print debug level. 0: no print, 1: standard, 2: verbose, 3: all messages'),
    "--exposure-time-us": dict(type=int,default=10,help='Exposure time (shutter time) in microseconds'),
    "--scan":dict(type=int, required = True, nargs=3, help='Enter the threshold scan start, stop and step'),
    "--type":dict(choices=['electrons','dac_code'],default='electrons',help='Define the type of the threshold scan'),
    '--repeat':dict(required=False,type=int,default=1,help='Number of repetitions per threshold sample'),
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
    dacs = dacs.DACs(tpx4,helpers.cl_chip_idx(),debug=True, load_dacs=False)

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

    #Save output parameters
    output['exposure time (us)'] = ns.exposure_time_us
    output['start'] = ns.scan[0]
    output['stop'] = ns.scan[1]
    output['step'] = ns.scan[2]
    output['scan type'] = ns.type

    # Create the hdf5 output file
    out_hdf5 = hdf5.hdf5_nexus(os.path.join(output['fullpath'],'th-scan.hdf5'),serial_number = ctrl.GetChipBoardInfo(rpc.EMPTY).serial)

    #Append metadata to output file
    out_hdf5.write_metadata(output)

    #Create output for dacs readback values
    output_dacs = {}

    #Append dacs to output_dacs
    for dac in dacs.dacs.keys():
        output_dacs[f'{dac} readback (V)'] = dacs.dacs[dac]['readback']
        output_dacs[f'{dac} dac code'] = dacs.dacs[dac]['dac_code']
    out_hdf5.write_metadata(output_dacs)

    #Create output data dictionary
    output_data = {}

    #Build the threshold array to iterate
    if ns.type == 'electrons':
        output_data['Threshold Target (e)'] = np.arange(output['start'], output['stop'] + output['step'], output['step'])
        iterator = output_data['Threshold Target (e)']
    else:
        output_data['Threshold DAC code Target'] = np.arange(output['start'], output['stop'] + output['step'], output['step'])
        iterator = output_data['Threshold DAC code Target']

    data_len = len(iterator)

    output_data['Threshold Readback'] = np.zeros(data_len)

    output_data['Threshold DAC readback (V)'] = np.zeros(data_len)
    output_data['FBK DAC readback (V)'] = np.zeros(data_len)
    output_data['Threshold DAC code'] = np.zeros(data_len)

    output_data['Counts Sum'] = np.zeros(data_len)
    output_data['Maximum Counts'] = np.zeros(data_len)
    output_data['Mean Counts'] = np.zeros(data_len)

    # It is necessary to create all datasets before open hdf5 file
    out_hdf5.create_2D_datasets(output_data,'Threshold DAC code',x_units = 'dac steps')

    #Valid images array
    images = []

    #Create an image
    img = np.zeros((512,448))

    for index,setpoint in enumerate(iterator):
        # Configure threshold in e. Polarity = 0 means electrons collection
        print('-----------------------------------------------------------')
        if ns.type == 'electrons':
            output_data['Threshold Readback'][index] = dacs.conf_threshold(THR_e=setpoint,debug=True)
        else:
            output_data['Threshold Readback'][index] = dacs.conf_threshold_dac_code(dac_code=setpoint,debug=True)

        output_data['Threshold DAC readback (V)'][index] = dacs.dacs['VThreshold']['readback']
        output_data['FBK DAC readback (V)'][index] = dacs.dacs['VFBK']['readback']
        output_data['Threshold DAC code'][index] = dacs.dacs['VThreshold']['dac_code']

        for i in range(ns.repeat):

            print(f'Threshold scan step {index+1}/{data_len}: Setpoint {setpoint} {ns.type}. Threshold measured {output_data['Threshold Readback'][index]:.2f} e. Repetition {i+1}/{ns.repeat}')

            #clear start flags
            start_event_top.clear()
            start_event_bot.clear()

            #wait start events to send a shutter during a valid frame
            start_event_top.wait()
            start_event_bot.wait()

            #send the shutter
            trigger.StartAutoShutter(rpc.EMPTY)             # Start auto-shutter

            with lock:
                shutter_open_frame = current_frame+1

            #Wait trigger to finish
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
            images.append(img)
            #And save it to the HDF5 file
            out_hdf5.append_image(img,field='data')

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

    #wait threads to finish
    capture_thread_top.join()
    capture_thread_bot.join()

    if ns.save_crw_frames == True:
        # Concatenate bottom and top matrixes to construct full images
        for i in range(min(len(decoder_top.frames),len(decoder_bot.frames))):
            frame = np.concatenate((decoder_bot.frames[i], np.rot90(decoder_top.frames[i], 2)), axis = 0)
            out_hdf5.append_image(frame,field='CRWframes')

    #Sum the counts of valid images
    counter_sum = np.sum(images,axis=(1,2))
    counter_max = np.max(images,axis=(1,2))
    counter_mean = np.mean(images,axis=(1,2))

    for i in range(data_len):
        output_data['Counts Sum'][i] = np.sum(counter_sum[i*ns.repeat:(i+1)*ns.repeat])/ns.repeat
        output_data['Maximum Counts'][i] = np.max(counter_max[i*ns.repeat:(i+1)*ns.repeat])
        output_data['Mean Counts'][i] = np.mean(counter_mean[i*ns.repeat:(i+1)*ns.repeat])

    #Sort arrays accordingly to the readback threshold
    sorted_indexes = np.argsort(output_data['Threshold DAC code'])
    for key in output_data.keys():
        output_data[key] = output_data[key][sorted_indexes]

    # Edit 2D datasets values
    out_hdf5.fill_2D_datasets(output_data)

    #Close the HDF5 file
    out_hdf5.close()

    #Get the polarity to reverse matplotlib x_axis (configured in the chip readout config)
    readout_config = tpx4.ReadoutGetConfig(rpc.ChipIndex(idx=helpers.cl_chip_idx()))

    #Plot the figure
    plt.figure()
    plt.plot(output_data['Threshold DAC code'],output_data['Counts Sum'],'-o')
    plt.title(f'Threshold Scan - {ns.exposure_time_us} us exposure')
    plt.xlabel('Threshold (dac codes)')

    #Reverse x axis for hole polarity
    if readout_config.polarity: plt.gca().invert_xaxis()

    plt.ylabel('Counts Sum')
    plt.grid()
    plt.tight_layout()
    plt.savefig(os.path.join(output['fullpath'],'th-scan.png'))
    plt.show()