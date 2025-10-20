#!/usr/bin/env python3

#############################################################################################################
#
#  tpx4_load_equalization.py
#  
#  Load equalization to the Timepix4
#
#
#  Authors: 
#   Matheus Gimenez Fernandes <matheus.fernandes@lnls.br>
#   Mauricio Donatti <mauricio.donatti@lnls.br>
#
#  August 2025
#
#############################################################################################################

#Import python native packages
import sys
import os
import numpy as np
from argparse import ArgumentTypeError

sys.path.insert(0, os.path.join(os.getcwd(),'..','common'))
sys.path.insert(0, os.path.join(os.getcwd(),'..'))

#Import spidr4py packages
from spidr4 import rpc, tpx4tools

#Import custom repository modules
import helpers

ARRAY_SIZE_X = 448
ARRAY_SIZE_Y = 512

def parse_tuples_pairs(s):
    try:
        parts = s.replace('(','').replace(')','').split(',')
        if len(parts) != 2:
            raise ValueError("Pixels must have exactly two elements.")
        x = int(parts[0].strip())
        if x >= ARRAY_SIZE_X: raise ValueError(f"X={x} exceeds array size {ARRAY_SIZE_X}")
        y = int(parts[1].strip())
        if y >= ARRAY_SIZE_Y: raise ValueError(f"Y={y} exceeds array size {ARRAY_SIZE_Y}")
        return (x,y)
    except ValueError as e:
        raise ArgumentTypeError(f"Invalid format: {s}. Error: {e}")

ns = helpers.cl_parse(with_chip_idx=True, args={
    '--equalization-path':dict(type=str,default='equalization',help='path to equalization files'),
    '--dac-codes-file':dict(type=str,default='eq_codes_fb.dat',help='path to dac codes file'),
    '--mask-file':dict(type=str,default='eq_mask_fb.dat',help='path to mask bit file'),
    '--to-mask':dict(type=parse_tuples_pairs,default=(),nargs='+',help='mask additional pixels. Send pixels as tuples: (X1,Y1) (X2,Y2)'),
})

# # Main loop, create network connection
with helpers.cl_connect() as channel:

    # Get the services
    # ------------------------------------------------------------------------------------------------------
    tpx4 = rpc.Timepix4Stub(channel)

    # Configure Pixel Matrix - load equalization and mask bits
    # ------------------------------------------------------------------------------------------------------
    mask_file = ns.mask_file
    eq_file = ns.dac_codes_file
    if os.path.isdir(ns.equalization_path) and os.path.isfile(os.path.join(ns.equalization_path,eq_file)) and os.path.isfile(os.path.join(ns.equalization_path,mask_file)):

        print(f'Loading equalization directory: {ns.equalization_path}')
        print(f'Loading dac codes from {eq_file}')
        print(f'Loading mask bits from {mask_file}')
        print('------------------------------------------------------------------------------------------------------------')

        pixel_cfg_mtx = np.zeros((ARRAY_SIZE_Y, ARRAY_SIZE_X), dtype=np.uint8)

        #loads equalization and mask bits from file
        mask=np.loadtxt(os.path.join(ns.equalization_path,mask_file), dtype=np.bool)
        equal=np.loadtxt(os.path.join(ns.equalization_path,eq_file), dtype=int)

        #configure pixels and calculate number of masked ones
        num_mask_pixels=0

        for X in range(0,ARRAY_SIZE_X,1):
            for Y in range(0,ARRAY_SIZE_Y,1):
                if (X,Y) in ns.to_mask:
                    mask[X][Y] = True
                    print(f'Masking extra pixel X={X} Y={Y}')
                pixel_cfg_mtx[Y][X] = tpx4tools.PixelConfig(dac=equal[X][Y], power_enable=not(mask[X][Y]), tp_enable=False, mask=mask[X][Y]).word
                #print(f'Pixel X:{X:03d} Y:{Y:03d} Equal: 0x{equal[X][Y]:02X} or {equal[X][Y]:02d} Mask: {mask[X][Y]}. Pixel cfg: 0x{pixel_cfg_mtx[Y][X]:02X} or {pixel_cfg_mtx[Y][X]:02d}')
                if mask[X][Y]:
                    num_mask_pixels+=1
        print(f'Num masked pixels: {num_mask_pixels}/{ARRAY_SIZE_X*ARRAY_SIZE_Y} = {100*num_mask_pixels/(ARRAY_SIZE_X*ARRAY_SIZE_Y):.3f}%')

        #Serialize pixel config data
        config_blob = tpx4tools.logic2chip_cfg_matrix(pixel_cfg_mtx)

        #Send pixel configuration to the ASIC
        tpx4.ConfigPixels(
                rpc.Tpx4PixelConfig(
                        idx=helpers.cl_chip_idx(),
                        config=config_blob.tobytes()
                )
        )
    else:
        print(f"ERROR: {ns.equalization_path} is not a valid path or equalization files not found. Aborting equalization")