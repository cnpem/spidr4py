#!/bin/env python3
#
# This example configures the Timepix4 over 10 Gb Ethernet and triggers an acquisition (current 10us exposure time)
#
# Example using sdaq to save TOP data:  sdaq 10.255.250.4:8192
# Example using sdaq to save TOP and BOTTOM data:  sdaq 10.255.250.4:8192,8193
#
#
#
import threading

import grpc
import sys
import time

import numpy as np
from spidr4 import rpc, tpx4tools, utils, stream
import helpers

ns = helpers.cl_parse(with_chip_idx=True, args={
    "iface": dict(help="Network interface", type=str),
    "--xgbe-port": dict(help="10 GbE port", type=int, default=8192)
})

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

    # Reset the pixel chips (will also load the default configuration)
    # ------------------------------------------------------------------------------------------------------
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
        mode=rpc.TPX4_READOUT_FRAME8,
        pc24b_thr=100
    )
    tpx4.ReadoutSetConfig(readoutCfg)

    # Configure shutter
    # ------------------------------------------------------------------------------------------------------
    tpx4.ShutterSetConfig(
        rpc.Tpx4ShutterConfig(
            idx=helpers.cl_chip_idx(),
            mode=rpc.TPX4_SHUTTER_MODE_PROG_SINGLE,
            input=rpc.TPX4_SHUTTER_INPUT_SLOW_CONTROL,
            prog_open_us=10,
            prog_close_us=1
        )
    )

    '''
    # Configure Trigger
    # ------------------------------------------------------------------------------------------------------
    tpx4.SetConfig(
        rpc.TriggerConfig(
            idx=helpers.cl_chip_idx(),
            shutter_input=rpc.SHUTTER_IN_SOFTWARE,
            t0_input=rpc.T0SYNC_IN_SOFTWARE,
            #Works only with SHUTTER_IN_AUTO_GEN or SHUTTER_IN_AUTO_GEN_EXT_START
            #auto_shutter_open_us=10,
            #auto_shutter_close_us=10,
            #####################################################################################
            shutter_count=1,
        )
    )'''
    time.sleep(1)


    tpx4.ShutterOpen(rpc.ChipIndex(idx=helpers.cl_chip_idx()))
    tpx4.T0Sync(rpc.ChipIndex(idx=helpers.cl_chip_idx()))


    time.sleep(1)
    # Reset the pixel chips (will also load the default configuration)
    # ------------------------------------------------------------------------------------------------------
    ctrl.ResetPixelChips(rpc.EMPTY)