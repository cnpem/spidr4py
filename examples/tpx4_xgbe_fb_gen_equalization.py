#!/usr/bin/env python3

#############################################################################################################
#
#  tpx4_xgbe_fb_gen_equalization.py
#
#  Performs frame-based acquisitions to generate the equalization and mask bits matrix.
#
#  Authors:
#   Mauricio Donatti <mauricio.donatti@lnls.br>
#
#  November 2025
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
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
import subprocess

sys.path.insert(0, os.path.join(os.getcwd(),'..'))

#Import spidr4py packages
from spidr4 import rpc,utils,tpx4tools,stream

#Import custom repository modules
import helpers
import fb_modules
from common import dacs

#Global shared variables and semaphore
current_frame = 0
lock = threading.Lock()

#Define chip size
ARRAY_SIZE_X = 448
ARRAY_SIZE_Y = 512

#create a default encoer to save JSON from numpy types
#JSON dumps need to encode numpy objects
def numpy_encoder(obj):
    if type(obj).__module__ == np.__name__:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return obj.item()
    raise TypeError('Unknown type:', type(obj))

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
    for data in stream.queue_generator(q, 40):
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
    '--path':dict(type=str,default='results',help='path to output files'),
    '--testname':dict(type=str,default='equalization',help='test name to create results directory'),
    '--debug':dict(type=int,choices=range(4),default=0,help='Print debug level. 0: no print, 1: standard, 2: verbose, 3: all messages'),
    "--exposure-time-us": dict(type=int,default=2000,help='Exposure time (shutter time) in microseconds'),
    '--repeat':dict(required=False,type=int,default=5,help='Number of repetitions per dac step'),
    '--dac-mode': dict(help='Select DAC mode to be loaded', default = 'fb_default', type=str),
    '--th-hot-e':dict(type=int,default=1000,help='Threshold to look for hot pixels in e-'),
    '--exposure-time-hot-us':dict(type=int,default=5e3,help='Exposure time to look for hot pixels in microseconds'),
    '--repeat-hot':dict(required=False,type=int,default=20,help='Number of image repetitions for hot pixels search')
})

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

#Call frame based configuration script resetting the chip
ans = os.system(f"python3 tpx4_fb_config_fast.py {ns.iface} --host {ns.host} \
    --port {ns.port} --chip-idx {ns.chip_idx} --no-ffly-mode --xgbe-port {ns.xgbe_port} \
    --crw-time-us 500000 --counter 16bit --reset --th_e 0 --gain high --no-status-packets \
    --polarity e --dac-mode {ns.dac_mode}")

if ans != 0:
    print(f'ERROR: running tpx4_fb_config_fast.py: {ans}')
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

    #Instantiate DAC class without initialize DACs (do not override configuration from tpx4_fb_config_fast.py script)
    # ------------------------------------------------------------------------------------------------------
    dacs = dacs.DACs(tpx4,helpers.cl_chip_idx(),adc_half='TOP',adc='internal',debug=True, initialize=False, dac_mode=ns.dac_mode)

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
    decoder_top = fb_modules.Packet2Frame(debug=ns.debug,use_shutter_control_packets=False)
    decoder_bot = fb_modules.Packet2Frame(debug=ns.debug,use_shutter_control_packets=False)

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

    #Create output data dictionary
    output_data = {}

    #Create the dac codes array
    output_data['dac_codes'] = range(0,32,1)

    #Build the threshold array to iterate
    valid_frames = []

    #create the config matrix array
    pixel_cfg_mtx = np.zeros((ARRAY_SIZE_Y, ARRAY_SIZE_X), dtype=np.uint8)

    for dac_code in output_data['dac_codes']:

        # Remark: threshold is set to 0 e by tpx4_fb_config_fast.py script
        print('-----------------------------------------------------------')
        print(f'Sending dac_code {dac_code} to the chip')

        for X in range(0,ARRAY_SIZE_X,1):
            for Y in range(0,ARRAY_SIZE_Y,1):
                pixel_cfg_mtx[Y][X] = tpx4tools.PixelConfig(dac=dac_code, power_enable=True, tp_enable=False, mask=False).word

        #Serialize pixel config data
        config_blob = tpx4tools.logic2chip_cfg_matrix(pixel_cfg_mtx)

        #Send pixel configuration to the ASIC
        tpx4.ConfigPixels(
                rpc.Tpx4PixelConfig(
                        idx=helpers.cl_chip_idx(),
                        config=config_blob.tobytes()
                )
        )

        for i in range(ns.repeat):

            print(f'Dac code value {dac_code}. Repetition {i+1}/{ns.repeat}')

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

    status = trigger.GetStatus(rpc.EMPTY)           # get trigger status
    print(f"Shutter total count: {status.shutter_counter}")

    print(f'Valid frames: {valid_frames}')

    # Concatenate botton and top matrixes to construct full images, considering valid frames
    output_data['equalization images'] = []
    for i in valid_frames:
        output_data['equalization images'].append(np.concatenate((decoder_bot.frames[i], np.rot90(decoder_top.frames[i], 2)), axis = 0))

    # Normalize the dac step repeated images
    normalized_images = []
    for i in output_data['dac_codes']:
        normalized_images.append(np.sum(output_data['equalization images'][i*ns.repeat:(i+1)*ns.repeat],axis=0)/ns.repeat)

    # Create auxiliary matrix to obtain the best equalization codes

    # Matrix of maximum counts
    output_data['max_count']=np.zeros(shape=(ARRAY_SIZE_Y,ARRAY_SIZE_X), dtype='int')

    # Matrix of pixel threshold config values (0 to 31)
    output_data['equalization_code']=np.zeros(shape=(ARRAY_SIZE_Y,ARRAY_SIZE_X), dtype='int')
    output_data['equalization_code'].fill(-1) #Fill with -1 to identify pixels to be masked

    # Matrix of masked pixels
    output_data['masked']=np.zeros(shape=(ARRAY_SIZE_Y,ARRAY_SIZE_X), dtype=bool)
    output_data['dead_pixels']=np.zeros(shape=(ARRAY_SIZE_Y,ARRAY_SIZE_X), dtype=bool)

    # Find dac_code that maximizes noise
    for dac_code in output_data['dac_codes']:
        for X in range(0,ARRAY_SIZE_X,1):
            for Y in range(0,ARRAY_SIZE_Y,1):
                if output_data['max_count'][Y][X]<normalized_images[dac_code][Y][X]:
                    output_data['max_count'][Y][X]=normalized_images[dac_code][Y][X]
                    output_data['equalization_code'][Y][X]=dac_code

    output['dead pixels number'] = 0
    # Writes threshold config value 15 and mask dead pixels
    for X in range(0,ARRAY_SIZE_X,1):
        for Y in range(0,ARRAY_SIZE_Y,1):
            if output_data['max_count'][Y][X] == 0:
                output_data['dead_pixels'][Y][X]=1
                output_data['equalization_code'][Y][X]=15
                output['dead pixels number'] += 1

    #Search for hot pixels
    # ------------------------------------------------------------------------------------------------------
    #Load equalization
    print('Fill equalization matrix')
    for X in range(0,ARRAY_SIZE_X,1):
        for Y in range(0,ARRAY_SIZE_Y,1):
            pixel_cfg_mtx[Y][X] = tpx4tools.PixelConfig(dac=output_data['equalization_code'][Y][X], power_enable=not(output_data['dead_pixels'][Y][X]), tp_enable=False, mask=output_data['dead_pixels'][Y][X]).word

    #Serialize pixel config data
    config_blob = tpx4tools.logic2chip_cfg_matrix(pixel_cfg_mtx)

    #WARNING: it has been found that send equalization to the chip during readout causes a bug, this can be a Spidr4
    #   fw issue, but still need to be investigated
    # ------------------------------------------------------------------------------------------------------
    #clear start flags
    start_event_top.clear()
    start_event_bot.clear()
    #wait the current frame to finish
    start_event_top.wait()
    start_event_bot.wait()
    # ------------------------------------------------------------------------------------------------------

    print('Loading equalization to the chip')
    #Send pixel configuration to the ASIC
    tpx4.ConfigPixels(
            rpc.Tpx4PixelConfig(
                    idx=helpers.cl_chip_idx(),
                    config=config_blob.tobytes()
            )
    )

    print(f'Configure threshold to {ns.th_hot_e} e-.')
    # Configure threshold in e. Polarity = 0 means electrons collection
    dacs.conf_threshold(THR_e=ns.th_hot_e,debug=True)

    print('Reconfigure Spidr4 shutter')
    #Configure shutter
    trigger.StopAutoShutter(rpc.EMPTY)              # Just in case it was still running
    # Configure Trigger
    # ------------------------------------------------------------------------------------------------------
    trigger.SetConfig(
        rpc.TriggerConfig(
            shutter_input=rpc.SHUTTER_IN_AUTO_GEN,
            t0_input=rpc.T0SYNC_IN_SOFTWARE,
            #Works only with SHUTTER_IN_AUTO_GEN or SHUTTER_IN_AUTO_GEN_EXT_START
            auto_shutter_open_us=ns.exposure_time_hot_us,
            auto_shutter_close_us=500000-ns.exposure_time_hot_us, #Configured as CRW wait time to avois arbitrador bug
            shutter_count=ns.repeat_hot,
            ####################################################################################
        )
    )
    trigger.ResetShutterCounter(rpc.EMPTY)          # Reset shutter counter

    print('Starting hot pixel search.')

    #Get current frame as the first one valid
    with lock:
        first_frame_hot_search = current_frame

    #send the shutter
    trigger.StartAutoShutter(rpc.EMPTY)             # Start auto-shutter
    status = trigger.GetStatus(rpc.EMPTY)           # get trigger status
    last_shutter = status.shutter_counter
    while status.auto_shutter_busy:
        time.sleep(0.1)
        status = trigger.GetStatus(rpc.EMPTY)       # Get the current status
        if status.shutter_counter != last_shutter:
            print(f'Hot pixel search. Exposure {ns.exposure_time_hot_us} us. {status.shutter_counter} shutter of {ns.repeat_hot} images')
            last_shutter = status.shutter_counter

    #Get last frame
    with lock:
        last_frame_hot_search = current_frame + 1

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

    # Concatenate bottom and top matrixes to construct full images, considering valid frames
    output_data['images hot search'] = []
    for i in range(first_frame_hot_search,last_frame_hot_search+1):
        output_data['images hot search'].append(np.concatenate((decoder_bot.frames[i], np.rot90(decoder_top.frames[i], 2)), axis = 0))

    #Create hot pixels matrix and counter
    output_data['hot_pixels']=np.sum(output_data['images hot search'],axis=0)>0
    output['hot pixels number'] = np.sum(output_data['hot_pixels'])

    #Compute mask pixels as dead or hot pixels
    # ------------------------------------------------------------------------------------------------------
    output_data['masked'] = np.logical_or(output_data['dead_pixels'],output_data['hot_pixels'])

    output_data['masked_coordinates']=np.argwhere(output_data['masked']>0)

    output['Number of masked'] = len(output_data['masked_coordinates'])
    output['Percentual masked'] = 100*output['Number of masked']/(ARRAY_SIZE_X*ARRAY_SIZE_Y)
    # Prints information of masked pixels
    #for Y,X in output_data['masked_coordinates']:
    #    print(f"mask ({X},{Y}): max count {output_data['max_count'][Y][X]} equalization code {output_data['equalization_code'][Y][X]}")
    print(f"Dead pixels number: {output['dead pixels number']}\t Hot pixels number: {output['hot pixels number']}")
    print(f"Total of masked pixels: {output['Number of masked']}/{ARRAY_SIZE_X*ARRAY_SIZE_Y} = {output['Percentual masked']:.2f} %")

    #Calculate the histogram of DAC codes
    output_data['dac_code_histogram'] = np.zeros(len(output_data['dac_codes']))
    for X in range(0,ARRAY_SIZE_X,1):
        for Y in range(0,ARRAY_SIZE_Y,1):
            if output_data['masked'][Y][X] == 0:
                output_data['dac_code_histogram'][output_data['equalization_code'][Y][X]] += 1

    print(f'Total of non-masked pixels: {np.sum(output_data['dac_code_histogram'])}')

    # Save equalization and mask bits matrix
    # ------------------------------------------------------------------------------------------------------
    # Create equalization path dir based on chipboard serial and chip_id
    output['equalization path'] = os.path.join(os.getcwd(),'config',carrier.serial,f'{chip.chip_id:08x}')
    os.makedirs(output['equalization path'],exist_ok=True)

    print(f'Saving dac_codes and mask bits files to: {output['equalization path']}')
    # Save in both directories
    for dir in [output['equalization path'],output['fullpath']]:
        np.savetxt(os.path.join(dir,'eq_mask_fb.dat'), output_data['masked_coordinates'] , fmt="%d", header = 'Masked Pixels in (Y,X) format')
        np.savetxt(os.path.join(dir,'eq_codes_fb.dat'), output_data['equalization_code'] , fmt="%d", header = 'DAC codes equalization (Y=512,X=448) matrix')

    # Save output files
    # ------------------------------------------------------------------------------------------------------
    print(f'Saving output hdf5: {os.path.join(output['fullpath'],'equalization.hdf5')}')
    # Save images in a .hdf5 file
    with h5py.File(os.path.join(output['fullpath'],'equalization.hdf5'), mode = 'w') as hdf5_file:
        for key in output.keys():
            hdf5_file.attrs[key] = output[key]
        for key in output_data.keys():
            hdf5_file.create_dataset(f'/entry/data/{key}', data = output_data[key])

    #Plot the histogram
    plt.figure()
    plt.bar(output_data['dac_codes'], output_data['dac_code_histogram'], width=1)
    plt.title(f'Equalization DAC codes histogram')
    plt.xlabel('Optimized DAC code')
    plt.ylabel('Number of Pixels')
    plt.grid()
    plt.tight_layout()
    plt.savefig(os.path.join(output['fullpath'],'dac_codes_histogram.png'))
    plt.show()

    #Plot masked pixels matrix
    plt.figure()
    # Define colors for different ranges (blue for healthy pixels, yellow for dead and red for hot)
    cmap = LinearSegmentedColormap.from_list("my_cmap", ['blue', 'yellow', 'red'])
    norm = BoundaryNorm([0, 1, 2, 3], cmap.N)
    plt.imshow(2*output_data['hot_pixels']+output_data['dead_pixels'],origin='lower',cmap=cmap, norm=norm)
    plt.title(f'{output['Number of masked']} masked pixels matrix. {output['Percentual masked']:.2f} %\n{output['dead pixels number']} dead and {output['hot pixels number']} hot pixels')
    cbar = plt.colorbar()
    cbar.ax.set_yticks([0.5, 1.5, 2.5],labels=['Normal Pixels','Dead Pixels','Hot Pixels'])
    plt.savefig(os.path.join(output['fullpath'],'masked_pixels.png'))
    plt.show()