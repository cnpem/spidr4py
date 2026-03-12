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
    '--equalization-path':dict(type=str,default='config/{chipboard_serial_number}/{chip_id}/',help='path to equalization files'),
    '--dac-codes-file':dict(type=str,default='eq_codes_fb.dat',help='dac codes filename'),
    '--mask-file':dict(type=str,default='eq_mask_fb.dat',help='mask bit filename'),
    '--to-mask':dict(type=parse_tuples_pairs,default=(),nargs='+',help='mask additional pixels. Send pixels as tuples: Y1,X1 Y2,X2'),
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
    if ns.equalization_path == 'config/{chipboard_serial_number}/{chip_id}/':
        #get the control service
        ctrl = rpc.ControlInfoStub(channel)
        #get chipboard carrier information
        carrier = ctrl.GetChipBoardInfo(rpc.EMPTY)
        #get chips information
        chips = ctrl.GetPixelChipInfo(rpc.EMPTY)
        #consider a single ASIC connected in position 0
        chip = chips.items[0]
        config_dir = f'config/{carrier.serial}/{chip.chip_id:08x}/'
    else:
        config_dir = ns.equalization_path

    if os.path.isdir(config_dir) and os.path.isfile(os.path.join(config_dir,eq_file)) and os.path.isfile(os.path.join(config_dir,mask_file)):

        print(f'Loading equalization directory: {config_dir}')
        print(f'Loading dac codes from {eq_file}')
        print(f'Loading mask bits from {mask_file}')
        print('------------------------------------------------------------------------------------------------------------')

        pixel_cfg_mtx = np.zeros((ARRAY_SIZE_Y, ARRAY_SIZE_X), dtype=np.uint8)

        #loads equalization and mask bits from file
        mask_coordinates=np.loadtxt(os.path.join(config_dir,mask_file), dtype=int)
        equal=np.loadtxt(os.path.join(config_dir,eq_file), dtype=int)

        #Create a boolean array to convert coordinates to a matrix
        mask_matrix=np.zeros(shape=(ARRAY_SIZE_Y,ARRAY_SIZE_X), dtype=bool)

        for (y,x) in mask_coordinates:
            mask_matrix[y,x] = True
        for (y,x) in ns.to_mask:
            mask_matrix[y,x] = True

        #Configure individual pixel config
        for X in range(0,ARRAY_SIZE_X,1):
            for Y in range(0,ARRAY_SIZE_Y,1):
                pixel_cfg_mtx[Y][X] = tpx4tools.PixelConfig(dac=equal[Y][X], power_enable=not(mask_matrix[Y,X]), tp_enable=False, mask=mask_matrix[Y,X]).word

        num_mask_pixels = np.sum(mask_matrix)
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
        print(f"ERROR: {config_dir} is not a valid path or equalization files not found. Aborting equalization")