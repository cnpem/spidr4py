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

import numpy as np
from spidr4 import rpc, tpx4tools, utils, stream
import helpers
from argparse import BooleanOptionalAction

PACKET_READ_BOTTOM= 0x4204
PACKET_READ_TOP= 0xC204

counter_options = ['8bit','16bit']

ns = helpers.cl_parse(with_chip_idx=True, args={
    "iface": dict(help="Network interface", type=str),
    "--xgbe-port": dict(help="10 GbE port", type=int, default=8192),
    "--exposure-time-us": dict(type=int,default=10,help='Exposure time (shutter time) in microseconds'),
    "--crw-time-us": dict(type=int,default=1000,help='Continuous read-write time in microseconds'),
    '--counter': dict(choices=counter_options,default='8bit',help='Frame based counter depth'),
    '--reset': dict(action=BooleanOptionalAction,default=True,help='reset Timepix4 ASIC at the beginning'),
})

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

iface2find = ns.iface
xgbe_port = ns.xgbe_port

# Find network interface information
# -----------------------------------------------------------------------------------------------------------
# Get network card MAC address and IP address
xgbe_host_mac, xgbe_host_ip = utils.get_nic_info(iface2find)

# make-up an 10gbe IP for the spidr4 module, as long as it is not the same as xgbe_host_ip
xgbe_spidr_ip = utils.inc_ip(xgbe_host_ip)

print(f'Spidr4 IP: {xgbe_spidr_ip}')
print(f'Xgbe TOP port: {xgbe_port}')
print(f'Xgbe BOT port: {xgbe_port+1}')
print(f'Host IP: {xgbe_host_ip}')

# Main loop, create network connection
with helpers.cl_connect() as channel:
    # Get the services
    # ------------------------------------------------------------------------------------------------------
    ctrl = rpc.ControlInfoStub(channel)
    tpx4 = rpc.Timepix4Stub(channel)
    datastream = rpc.DataStreamStub(channel)
    trigger = rpc.TriggerStub(channel)

    # Configure Trigger
    # ------------------------------------------------------------------------------------------------------
    trigger.SetConfig(
        rpc.TriggerConfig(
            shutter_input=rpc.SHUTTER_IN_SOFTWARE,
            t0_input=rpc.T0SYNC_IN_SOFTWARE,
            #Works only with SHUTTER_IN_AUTO_GEN or SHUTTER_IN_AUTO_GEN_EXT_START
            #auto_shutter_open_us=10,
            #auto_shutter_close_us=10,
            #shutter_count=1,
            ####################################################################################
        )
    )

    # Reset the pixel chips (will also load the default configuration)
    # ------------------------------------------------------------------------------------------------------
    if ns.reset:
        print('Resetting the pixel chips (load default config)')
        ctrl.ResetPixelChips(rpc.EMPTY)

    # Configure the output
    # ------------------------------------------------------------------------------------------------------
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
    readoutCfg = rpc.Tpx4ReadoutConfig(
        idx=helpers.cl_chip_idx(),
        mode=rpc.TPX4_READOUT_FRAME8 if ns.counter == '8bit' else rpc.TPX4_READOUT_FRAME16,
        pc24b_thr=100
    )
    tpx4.ReadoutSetConfig(readoutCfg)

    start_frame_enable(en = False, top = True)
    start_frame_enable(en = False, top = False)

    # Configure shutter
    # ------------------------------------------------------------------------------------------------------
    tpx4.ShutterSetConfig(
        rpc.Tpx4ShutterConfig(
            idx=helpers.cl_chip_idx(),
            mode=rpc.TPX4_SHUTTER_MODE_PROG_SINGLE,
            input=rpc.TPX4_SHUTTER_INPUT_SLOW_CONTROL,
            prog_open_us=ns.exposure_time_us,
            prog_close_us=1,
        )
    )

    crw_regs = {
        'CRW_WAIT_TIME_TOP': 0xC202,
        'CRW_WAIT_TIME_BOTTOM': 0x4202,
    }

    #Calculate crw registers needed value:
    Nlinks = 1                 #default for spidr4 readout 10Gbps mode
    LinkSpeed_Mbps = 2560      #default for spidr4 readout 10Gbps mode
    clk_datapath_MHz = 160     #clk_datapath default config
    counter_depth = 8 if ns.counter == '8bit' else 16
    readout_time_frame_us = 256*448*counter_depth/(LinkSpeed_Mbps*Nlinks)
    crw_regs_val = int((ns.crw_time_us - readout_time_frame_us)*clk_datapath_MHz)
    print(f'Readout time per frame: {readout_time_frame_us} us. crw_wait_time register value: {crw_regs_val}')

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
        }

    for reg in registers.keys():
        
        ans = tpx4.ReadReg(
            rpc.ReadRegRequest(
                idx=0,
                addr=registers[reg],
            )
        )
        print(f'Register {reg:20} 0x{registers[reg]:02X}: 0b{int.from_bytes(ans.data):016b}')
    
    #Enable Control packets, like shutter to ensure image sync at post-processing
    registers_to_write = {
        'STATUS_MON_TOP': [0xCC02,0b0000000000000111],
        'STATUS_MON_BOT': [0x4C02,0b0000000000000111],
        'PPROC_TOP':[0xCC03,0b0100000000000000],
        'PPROC_BOT':[0x4C03,0b0100000000000000],
        }

    for reg in registers_to_write.keys():

        tpx4.WriteReg(
            rpc.WriteRegRequest(
                idx=0,
                addr=registers_to_write[reg][0],
                data=int(registers_to_write[reg][1]).to_bytes(2)
            )
        )
        ans = tpx4.ReadReg(
            rpc.ReadRegRequest(
                idx=0,
                addr=registers_to_write[reg][0],
            )
        )
        print(f'Register {reg:20} 0x{registers_to_write[reg][0]:02X}: 0b{int.from_bytes(ans.data):016b}')

    start_frame_enable(en = True, top = True)
    start_frame_enable(en = True, top = False)

    tpx4.ShutterOpen(rpc.ChipIndex(idx=helpers.cl_chip_idx()))
    tpx4.T0Sync(rpc.ChipIndex(idx=helpers.cl_chip_idx()))

    time.sleep(ns.exposure_time_us/1e6)

    start_frame_enable(en = False, top = True)
    start_frame_enable(en = False, top = False)
