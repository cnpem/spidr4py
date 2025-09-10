#!/usr/bin/env python3

#############################################################################################################
#
#  tpx4_fb_load_equalization.py
#  
#  Load equalization. Based on tpx4_fb_fast.py
#
#
#  Authors: 
#   Matheus Gimenez Fernandes <matheus.fernandes@lnls.br>
#   Mauricio Donatti <mauricio.donatti@lnls.br>
#
#  August 2025
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

# counter_options = ['8bit','16bit']
# available_link_speed = [40,80,160,320,640,1280,2560,5120,10240]

ns = helpers.cl_parse(with_chip_idx=True, args={
    "iface": dict(help="Network interface for Spidr4 10G link", type=str, nargs='?'),
    '--reset': dict(action=BooleanOptionalAction,default=True,help='reset Timepix4 ASIC at the beginning'),
    '--equalization-path':dict(type=str,default='equalization',help='path to input and output file'),
})

# # Main loop, create network connection
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
            auto_shutter_open_us=10,
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