#!/usr/bin/env python3

#############################################################################################################
#
#  tpx4_xgbe_fb.py
#  
#  Performs a frame-based acquisition using 10G interface
#
#  Authors: 
#   Mauricio Donatti <mauricio.donatti@lnls.br>
#
#  July 2025
#
#############################################################################################################

import threading

import grpc
import sys
import time
import os

import numpy as np
from spidr4 import rpc, tpx4tools, utils, stream
import helpers
from argparse import BooleanOptionalAction

sys.path.insert(0, os.path.join(os.getcwd(),'..','common'))
sys.path.insert(0, os.path.join(os.getcwd(),'..'))

from common import dacs

PACKET_READ_BOTTOM= 0x4204
PACKET_READ_TOP= 0xC204

counter_options = ['8bit','16bit']
available_link_speed = [40,80,160,320,640,1280,2560,5120,10240]

ns = helpers.cl_parse(with_chip_idx=True, args={
    "iface": dict(help="Network interface for Spidr4 10G link", type=str, nargs='?'),
    "--ffly-mode": dict(help="Use firefly links instead of the 10 GbE port", action=BooleanOptionalAction,default=False),
    '--channels-top': dict(type=lambda x: int(x,0),default=0xFF,choices=range(0,256),metavar='[0x00-0xFF]',help='Choose TOP channels to be enabled as hex 8bit'),
    '--channels-bot': dict(type=lambda x: int(x,0),default=0xFF,choices=range(0,256),metavar='[0x00-0xFF]',help='Choose BOTTOM channels to be enabled as hex 8bit'),
    '--link-speed-mbps': dict(type=int,choices=available_link_speed,default=2560,help='Link Speed in MHz'),
    "--xgbe-port": dict(help="10 GbE port", type=int, default=8192),
    "--exposure-time-us": dict(type=int,default=10,help='Exposure time (shutter time) in microseconds'),
    "--crw-time-us": dict(type=int,default=1000,help='Continuous read-write time in microseconds'),
    '--counter': dict(choices=['8bit','16bit'],default='8bit',help='Frame based counter depth'),
    '--reset': dict(action=BooleanOptionalAction,default=True,help='reset Timepix4 ASIC at the beginning'),
    '--equalize':dict(action=BooleanOptionalAction,default=True,help='load equalization'),
    '--status-packets':dict(action=BooleanOptionalAction,default=True,help='Enables sending output status packets in the data stream (for example, Shutter Rise/Fall)'),
    '--equalization-path':dict(type=str,default='equalization',help='path to input and output file'),
    '--th_e':dict(type=int,default=0,help='Threshold in e-'),
    '--polarity': dict(choices=['h','e'],default='e',help='Charge collection'),
    '--gain': dict(choices=['low','high'],default='high',help='CSA gain'),
})

if ns.iface == None and ns.ffly_mode == False:
    print("If not using --ffly-mode, the xgbe network interface name is required", file=sys.stderr)
    sys.exit(1)
elif ns.iface != None and ns.ffly_mode == True:
    print("Network interface should not be set when using --ffly-mode", file=sys.stderr)
    sys.exit(1)

def get_link_bw(top = True, check_PLL = False, optimize_PLL = False):

    #get high_BW_en at GWT_CONF register to check 160 or 320 MHz mode
    ans = tpx4.ReadReg(
        rpc.ReadRegRequest(
            idx=0,
            addr=0xC207 if top == True else 0x4207,
        )
    )
    high_bw_en = (int.from_bytes(ans.data) >> 24) & 0b1

    #get speed_div_log2 at PCSTX_CTRL register to check PLL divider
    ans = tpx4.ReadReg(
        rpc.ReadRegRequest(
            idx=0,
            addr=0xCC01 if top == True else 0x4C01,
        )
    )

    speed_div_log_2 = int.from_bytes(ans.data) & 0b1111

    if check_PLL: check_optimal_PLL(top = top, en_print=True)

    if optimize_PLL and not(check_optimal_PLL(top=top)):
        print('Optimizing PLL setting')
        ans = tpx4.WriteReg(
            rpc.WriteRegRequest(
                idx=0,
                addr=0xC208 if top == True else 0x4208,
                #      res_PLL    | icp_PLL   | adj_cp_PLL | adj_vco_PLL| cap_small_PLL | cap_large_PLL | rst_vcntr_vdd_PLL
                data= (0b1110<<27 | 0b111<<24 | 0b1111<<20 | 0b0000<<16 | 0b1111<<12    | 0b0011<<8     | 0x00).to_bytes(4)
            )
        )

    return 5120*(2**(high_bw_en))/(2**(speed_div_log_2))

def check_optimal_PLL(top = True,en_print=False):
    if check_optimal_PLL:
        #get GWT_CONF_PLL register
        ans = tpx4.ReadReg(
            rpc.ReadRegRequest(
                idx=0,
                addr=0xC208 if top == True else 0x4208,
            )
        )
        reg_data = int.from_bytes(ans.data)
        #extract fields
        res_PLL = (reg_data>>27)&0xF
        icp_PLL = (reg_data>>24)&0b111
        adj_cp_PLL = (reg_data>>20)&0xF
        adj_vco_PLL = (reg_data>>16)&0xF
        cap_small_PLL = (reg_data>>12)&0xF
        cap_large_PLL = (reg_data>>8)&0xF
        rst_vcntr_vdd_PLL = (reg_data)&0xFF

        if en_print: print(f'res_PLL={res_PLL:04b}\t icp_PLL={icp_PLL:03b}\t adj_cp_PLL={adj_cp_PLL:04b}\t adj_vco_PLL={adj_vco_PLL:04b}\t cap_small_PLL={cap_small_PLL:04b}\t cap_large_PLL={cap_large_PLL:04b}\t rst_vcntr_vdd_PLL={rst_vcntr_vdd_PLL:08b}')

        if icp_PLL != 7 or adj_cp_PLL != 0xF or cap_small_PLL != 0xF:
            print(f'WARNING: {'Top' if top else 'Bottom'} PLL not optimized. See https://timepix4.web.cern.ch/timepix4/timepix4/ChipOperation/configuration_output_links.html')
            return False
        else:
            return True

def start_frame_enable(en = True, top = True):
    if top:
        reg = PACKET_READ_TOP
    else:
        reg = PACKET_READ_BOTTOM

    ans = tpx4.ReadReg(
        rpc.ReadRegRequest(
            idx=0,
            addr=reg,
        )
    )

    if en:
        data_en = (int.from_bytes(ans.data) | 0x0010).to_bytes(2)
    else:
        data_en = (int.from_bytes(ans.data) & 0xFFEF).to_bytes(2)

    tpx4.WriteReg(
        rpc.WriteRegRequest(
            idx=0,
            addr=reg,
            data=data_en
        )
    )

if ns.ffly_mode == False:
    iface2find = ns.iface
    xgbe_port = ns.xgbe_port

    # Find network interface information
    # Get network card MAC address and IP address
    xgbe_host_mac, xgbe_host_ip = utils.get_nic_info(iface2find)

    # make-up an 10gbe IP for the spidr4 module, as long as it is not the same as xgbe_host_ip
    xgbe_spidr_ip = utils.inc_ip(xgbe_host_ip)
    print(f'Xgbe TOP port: {xgbe_port}')
    print(f'Xgbe BOT port: {xgbe_port+1}')
    print(f'Spidr4 IP: {xgbe_spidr_ip}')
    print(f'Host IP: {xgbe_host_ip}')


# Main loop, create network connection
with helpers.cl_connect() as channel:
    # Get the services
    # ------------------------------------------------------------------------------------------------------
    ctrl = rpc.ControlInfoStub(channel)
    tpx4 = rpc.Timepix4Stub(channel)
    datastream = rpc.DataStreamStub(channel)
    trigger = rpc.TriggerStub(channel)

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
            auto_shutter_close_us=10,
            shutter_count=1,
            ####################################################################################
        )
    )
    trigger.ResetShutterCounter(rpc.EMPTY)          # Reset shutter counter

    # Reset the pixel chips (will also load the default configuration)
    # ------------------------------------------------------------------------------------------------------
    if ns.reset:
        print('Resetting the pixel chips (load default config)')
        ctrl.ResetPixelChips(rpc.EMPTY)
        #Reset the pixel matrix
        tpx4.PixelMatrixReset(rpc.ChipIndex(idx=helpers.cl_chip_idx()))

    #Configure DACs
    # ------------------------------------------------------------------------------------------------------
    dacs = dacs.DACs(tpx4,helpers.cl_chip_idx(),adc_half='TOP',adc='internal',debug=True)

    # Configure Pixel Matrix - load equalization and mask bits
    # ------------------------------------------------------------------------------------------------------
    if ns.equalize == True:
        mask_file = 'eq_mask_fb.dat'
        eq_file = 'eq_codes_fb.dat'
        if os.path.isdir(ns.equalization_path) and os.path.isfile(os.path.join(ns.equalization_path,eq_file)) and os.path.isfile(os.path.join(ns.equalization_path,mask_file)):

            print(f'Loading equalization')
            pixel_cfg_mtx = np.zeros((512, 448), dtype=np.uint8)

            #loads equalization and mask bits from file
            mask=np.loadtxt(os.path.join(ns.equalization_path,mask_file), dtype=np.bool)
            equal=np.loadtxt(os.path.join(ns.equalization_path,eq_file), dtype=int)

            #configure pixels and calculate number of masked ones
            num_mask_pixels=0
            for X in range(0,448,1):
                for Y in range(0,512,1):
                    pixel_cfg_mtx[Y][X] = tpx4tools.PixelConfig(dac=equal[X][Y], power_enable=not(mask[X][Y]), tp_enable=False, mask=mask[X][Y]).word
                    #print(f'Pixel X:{X:03d} Y:{Y:03d} Equal: 0x{equal[X][Y]:02X} or {equal[X][Y]:02d} Mask: {mask[X][Y]}. Pixel cfg: 0x{pixel_cfg_mtx[Y][X]:02X} or {pixel_cfg_mtx[Y][X]:02d}')
                    if mask[X][Y]:
                        num_mask_pixels+=1
            print(f'Num masked pixels: {num_mask_pixels}')

            config_blob = tpx4tools.logic2chip_cfg_matrix(pixel_cfg_mtx)

            tpx4.ConfigPixels(
                    rpc.Tpx4PixelConfig(
                            idx=helpers.cl_chip_idx(),
                            config=config_blob.tobytes()
                    )
            )
        else:
            print(f"ERROR: {ns.equalization_path} is not a valid path or equalization files not found. Aborting equalization")

    # Configure the output
    # ------------------------------------------------------------------------------------------------------
    if ns.ffly_mode:
        # Use optical links (FireFly) to stream raw Timepix4 data
        datastream.ConfigOptical(rpc.OpticalLinkConfig(
                idx=helpers.cl_chip_idx(),
                channels=(ns.channels_top << 8) | ns.channels_bot,
                link_speed=ns.link_speed_mbps
        ))
    else:
        # Use the 10 Gbps ethernet inteface to stream Timepix4 data
        datastream.ConfigXGbe(rpc.XGbeConfig(
            idx=0,
            primary=rpc.XGbeLinkConfig(
                source_ip=xgbe_spidr_ip,
                dest_ip=xgbe_host_ip,
                dest_mac=xgbe_host_mac,
                port=xgbe_port
            )
        ))

    # Configure frame-based readout
    # ------------------------------------------------------------------------------------------------------
    #See https://spidr4.nikhef.nl/docs/html/reference/grpc.html?highlight=tpx4readoutconfig#tpx4analogfrontendmode
    match (ns.gain.lower(),ns.polarity.lower()):
        case (g,p) if g == 'high' and p == 'e':
            afe_mode = rpc.TPX4_AFEM_HIGH_GAIN_ELECTRON_COLLECTION
        case (g,p) if g == 'high' and p == 'h':
            afe_mode = rpc.TPX4_AFEM_HIGH_GAIN_HOLE_COLLECTION
        case (g,p) if g == 'low' and p == 'e':
            afe_mode = rpc.TPX4_AFEM_LOW_GAIN_ELECTRON_COLLECTION
        case (g,p) if g == 'low' and p == 'h':
            afe_mode = rpc.TPX4_AFEM_LOW_GAIN_HOLE_COLLECTION
        case _:
            print(f'Error. Not supported gain {ns.gain}.')
            raise SystemError

    tpx4.ReadoutSetConfig(
        rpc.Tpx4ReadoutConfig(
            idx=helpers.cl_chip_idx(),
            mode=rpc.TPX4_READOUT_FRAME8 if ns.counter == '8bit' else rpc.TPX4_READOUT_FRAME16,
            toa_enable=False,
            analog_frontend_mode=afe_mode,
        )
    )

    # Configure threshold in e. Polarity = 0 means electrons collection
    dacs.conf_threshold(LOW_GAIN=ns.gain.lower()=='low',POLARITY=ns.polarity.lower()=='h',THR_e=ns.th_e,debug=True)

    # Configure status monitor configuration
    # ------------------------------------------------------------------------------------------------------
    tpx4.StatusMonSetConfig(
        rpc.Tpx4StatusMonConfig(
            idx=helpers.cl_chip_idx(),
            enable=ns.status_packets,                   #Enable status and monitoring packet generation (output status packets in the data stream)
            heartbeat=False,                            #Enable the heartbeat (periodical status packets)
            heartbeat_shift=0,                          #Heartbeat shift. A heartbeat is send every (1 << heatbeat_shift) * 25 ns.
            global_time_reset=False,                    #Resets the global time on T0-sync
            global_time=False,                          #Enable the glboal time counter in status packets (48bit)
            ctrl_data_test=False,                       #Enable sending constant data-test packets
            signal_select=rpc.TPX4_SIGNAL_SELECT_NONE,  #TPX4_SIGNAL_SELECT_NONE or TPX4_SIGNAL_SELECT_CRW_NEXT_FRAME
        )
    )

    # Configure shutter
    # ------------------------------------------------------------------------------------------------------
    tpx4.ShutterSetConfig(
        rpc.Tpx4ShutterConfig(
            idx=helpers.cl_chip_idx(),
            mode=rpc.TPX4_SHUTTER_MODE_MANUAL,  #change to TPX4_SHUTTER_MODE_PROG_SINGLE for internal controlled shutter,
            input=rpc.TPX4_SHUTTER_INPUT_PAD,   #change to TPX4_SHUTTER_INPUT_SLOW_CONTROL to trigger internal shutter using SC
            prog_open_us=ns.exposure_time_us,
            prog_close_us=1,
        )
    )

    # Configure the output links and optimize PLLs
    # ------------------------------------------------------------------------------------------------------

    link_top = get_link_bw(top = True,check_PLL=False,optimize_PLL=True)
    link_bot = get_link_bw(top = False,check_PLL=False,optimize_PLL=True)

    print(f'Link speed TOP: {link_top} Mbps')
    print(f'Link speed BOT: {link_bot} Mbps')

    #Calculate crw registers needed value:
    if ns.ffly_mode:
        # Get the maximum number of active optical links
        Nlinks = max(bin(ns.channels_top).count('1'), bin(ns.channels_bot).count('1'))
    else:
        # When using the 10 Gbps ethernet interface, only one link per top/bottom is active
        Nlinks = 1
    LinkSpeed_Mbps = get_link_bw(top = True)      #default for spidr4 readout 10Gbps mode
    clk_datapath_MHz = 160                        #clk_datapath default config
    counter_depth = 8 if ns.counter == '8bit' else 16
    readout_time_frame_us = 256*448*counter_depth/(LinkSpeed_Mbps*Nlinks)
    crw_regs_val = int((ns.crw_time_us - readout_time_frame_us)*clk_datapath_MHz)
    if crw_regs_val <= 0:
        print(f'ERROR: crw wait time to short for {LinkSpeed_Mbps} Mbps link speed. Setting to 1 cycle. {crw_regs_val} cannot be 0 or negative')
        crw_regs_val = 1
    print(f'Readout time per frame: {readout_time_frame_us} us. crw_wait_time register value: {crw_regs_val}')

    crw_regs = {
        'CRW_WAIT_TIME_TOP': 0xC202,
        'CRW_WAIT_TIME_BOTTOM': 0x4202,
    }

    #Configure CRW_WAIT_TIME Bottom and Top registers
    for reg in crw_regs.keys():
    
        tpx4.WriteReg(
            rpc.WriteRegRequest(
                idx=0,
                addr=crw_regs[reg],
                data=crw_regs_val.to_bytes(4)
            )
        )

        ans = tpx4.ReadReg(
            rpc.ReadRegRequest(
                idx=0,
                addr=crw_regs[reg],
            )
        )

        print(f'Register {reg:20}: {int.from_bytes(ans.data)} clock cycles, {int.from_bytes(ans.data)/(clk_datapath_MHz*1e6)} seconds')
        

    #Monitor a few registers to understand Timpeix4 behavior
    registers = {
        'MATRIX_SHUTTER':0x8061,
        'MATRIX_CRW_TOP':0xC206,
        'MATRIX_CRW_BOT':0x4206,
        'MATRIX_RST':0x8060,
        'STATUS_MON_TOP': 0xCC02,
        'STATUS_MON_BOT': 0x4C02,
        'PPROC_TOP':0xCC03,
        'PPROC_BOT':0x4C03,
        'GWT_CONF_TOP':0xC207,
        'GWT_CONF_BOT':0x4207,
        'GWT_CONF_PLL_TOP':0xC208,
        'GWT_CONF_PLL_BOT':0x4208,
        'PCSTX_CTRL_TOP':0xCC01,
        'PCSTX_CTRL_BOT':0x4C01,
        }

    for reg in registers.keys():
        
        ans = tpx4.ReadReg(
            rpc.ReadRegRequest(
                idx=0,
                addr=registers[reg],
            )
        )
        print(f'Register {reg:20} 0x{registers[reg]:02X}: 0b{int.from_bytes(ans.data):016b}')

    ############################################################################################
    # We're not disabling start_frame_enable to workaround 16bit bug: https://timepix4.web.cern.ch/timepix4/timepix4/ChipOperation/bugs_knowissues_and_faq.html#bit-mode-start
    ############################################################################################
    # Enable start_frame
    #start_frame_enable(en = True, top = True)
    #start_frame_enable(en = True, top = False)
    ############################################################################################
    #Send T0Sync if a reset has been performed to start readout

    if ns.reset: tpx4.T0Sync(rpc.ChipIndex(idx=helpers.cl_chip_idx()))

    print('Opening shutter')
    trigger.StartAutoShutter(rpc.EMPTY)             # Start auto-shutter

    status = trigger.GetStatus(rpc.EMPTY)           # Wait until it is done
    while status.auto_shutter_busy:
        time.sleep(0.1)
        status = trigger.GetStatus(rpc.EMPTY)       # Get the current status
        print(f"Shutter count: {status.shutter_counter}")

    ############################################################################################
    # Disable start_frame and stop readout
    #start_frame_enable(en = False, top = True)
    #start_frame_enable(en = False, top = False)
    ############################################################################################
