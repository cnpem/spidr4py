#!/usr/bin/env python3

#############################################################################################################
#
#  fb_decode.py
#  
#  Performs a frame-based decode
#
#  Authors: 
#   Allan Borgato <allan.borgato@lnls.br>
#   Mauricio Donatti <mauricio.donatti@lnls.br>
#
#  July 2025
#
#############################################################################################################

import numpy as np
import glob
import os
import h5py
import struct
import argparse
import time

def dir_path(path):
    if os.path.isdir(path):
        return path
    else:
        raise argparse.ArgumentTypeError(f"readable_dir:{path} is not a valid path")

#create a parser to properly parse script arguments
parser = argparse.ArgumentParser(
    prog='fb_decode.py',
    description='performs a Timepix4 frame based decode',
    epilog='This script interprets frame based data and save image files',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument('--path',type=dir_path,required=True,help='path to input and output file')
parser.add_argument('--save-file',action=argparse.BooleanOptionalAction,default=True,help='save hdf5 output file')
parser.add_argument('--ignore-shutter',action=argparse.BooleanOptionalAction,default=False,help='do not search for shutter rise/fall and decode all frames')
parser.add_argument('--filename',type=str,default='fb_decode',help='test name to be appended to output filename')
parser.add_argument('--debug',type=int,choices=range(3),default=1,help='Print debug level. 0: no print, 1: standard, 2: verbose')

args = parser.parse_args()

class bcolors:
    ERROR = '\033[91m'
    ENDC = '\033[0m'
    CONTROL = '\033[92m'
    WARNING = '\033[33m'
    DEBUG = '\033[94m'
    FRAME = "\033[95m"
    SDAQ = '\033[96m'

class DecodePacket:
    def __init__(self,packet):
        self.packet = packet
        
        self.top = (packet >> 63) & 0b1
        self.header = (packet >> 55) & 0xFF
        self.segment = (packet >> 52) & 0b111
        self.readout_mode = (packet >> 50) & 0b11
        
        #decode if the packet is from TOP or BOTTOM
        self.half = 'TOP' if self.top == True else 'BOT'

        #decode readout mode to find photon counter
        if self.readout_mode == 0b10:
            self.pc_mode = '8bit'
        elif self.readout_mode == 0b11:
            self.pc_mode = '16bit'
        else:
            self.pc_mode = 'unknown'

        #Use 8bit header to find control packet
        match self.header:
            case 0xE0:
                self.name = 'HEARTBEAT'
            case 0xE1:
                self.name = 'SHUTTER_RISE'
            case 0xE2:
                self.name = 'SHUTTER_FALL'
            case 0xE3:
                self.name = 'T0_SYNC'
            case 0xE4:
                self.name = 'SIGNAL_RISE'
            case 0xE5:
                self.name = 'SIGNAL_FALL'
            case 0xEA:
                self.name = 'CTRL_DATA_TEST'
            case 0xF0:
                self.name = 'FRAME_START' 
            case 0xF1:
                self.name = 'FRAME_END'
            case 0xF2:
                self.name = 'SEGMENT_START'
            case 0xF3:
                self.name = 'SEGMENT_END'
            case _:
                self.name = 'DATA'

        self.control = False if self.name == 'DATA' else True
    
        self.array8bit = struct.unpack('8B', packet)

filenames = sorted(glob.glob(os.path.join(args.path,'*.dat*'))) # SPIDR4 sdaq uses .dat
print(f'Reading files: {filenames}')

# Create a matrixes array to plot
matrixes = []

# For each binary file
for file in filenames:

    print('------------------------------------------------------------------------------------------------------------------------------------------------------------------------------')
    # Show wich file is being read
    print(f"Decoding File: {file}")

    # Creat new packets array to add
    packets = np.fromfile(file, dtype=np.uint64)

    # Create a frames array
    frames = []

    # Finite State Machine (FSM)
    state = 'IDLE' # 0 = IDLE, 1 = FRAME_STARTED, 2 = SEGMENT_STARTED
    
    # Indexes to control FSM
    frame_counter = 0
    data_counter = 0
    segment_counter = [0, 0, 0, 0, 0, 0, 0, 0]
    segment_address = 0
    shutter_rise = shutter_fall = False
    
    # Packet Coordinates (Pixel 0)
    x = 0
    y = 0

    loop_time = time.time()

    spidr_valid_frame = False
    # Analyze each packet in the file
    for packet_counter,packet in enumerate(packets):

        #Filter spidr4 headers and control packets
        #See https://spidr4.nikhef.nl/docs/html/software/dataformat.html
        if spidr_valid_frame == False and (packet & 0xFFFF000000000000) == 0x0002000000000000:
            spidr_valid_frame = True
            spidr_frame_counter = 0
            spidr_content_size = packet & 0xFFFFFFFF
            if args.debug >= 1: print(f'{bcolors.SDAQ}{packet_counter:06} - Spidr4 frame header packet: 0x{packet:016X}. Content size: {spidr_content_size} packets{bcolors.ENDC}')

        elif spidr_valid_frame == True:
            #Increment spidr frame counter and check if the current packet is the spidr frame end
            spidr_frame_counter+=1
            if spidr_frame_counter == spidr_content_size:
                spidr_valid_frame = False
                if args.debug >= 1: print(f'{bcolors.SDAQ}{packet_counter:06} - Spidr4 last frame packet. Counter {spidr_frame_counter}. Content size: {spidr_content_size} packets{bcolors.ENDC}')

            decoded_packet = DecodePacket(packet)

            # Look for Shutter Rise packet
            if decoded_packet.name == 'SHUTTER_RISE' and state != 'SEGMENT':
                shutter_rise = True
                shutter_fall = False
                if args.debug >= 1: print(f"{bcolors.CONTROL}{packet_counter:06} - {decoded_packet.half} 0x{decoded_packet.header:02X}: {decoded_packet.name}{bcolors.ENDC}")

            # Look for a shutter fall package
            elif decoded_packet.name == 'SHUTTER_FALL' and state != 'SEGMENT':
                if args.debug >= 1: print(f"{bcolors.CONTROL}{packet_counter:06} - {decoded_packet.half} 0x{decoded_packet.header:02X}: {decoded_packet.name}{bcolors.ENDC}")
                shutter_fall = True

            # FSM definition
            match state:

                case 'IDLE':
                    # Look for Frame Start packet
                    if decoded_packet.name == 'FRAME_START' and (shutter_rise or args.ignore_shutter):
                        readout_mode = decoded_packet.pc_mode
                        matrix = np.zeros((256, 448), dtype=np.uint8 if readout_mode == '8bit' else np.uint16)
                        if args.debug >= 1: print(f"{bcolors.FRAME}{packet_counter:06} - {decoded_packet.half} {decoded_packet.pc_mode} {decoded_packet.name}: Frame {frame_counter}.{bcolors.ENDC}")
                        state = 'FRAME'
                        #If we received a shutter fall, this one is the last frame
                        if shutter_fall == True:
                            shutter_rise = False
                    # See if a control packet arrived during Idle State
                    elif  args.debug >= 2 and decoded_packet.control == True:
                        print(f"{bcolors.WARNING}{packet_counter:06} - {decoded_packet.half} CONTROL PACKET 0x{decoded_packet.header:02X}: {decoded_packet.name}{bcolors.ENDC}")
                    
                case 'FRAME':
                    # Look for Segment Start packet
                    if decoded_packet.name == 'SEGMENT_START':
                        # Get the address of started segment
                        segment_address = decoded_packet.segment
                        # Start counting data packets read from the next segment
                        data_counter = 0
                        if args.debug >= 1: print(f"{packet_counter:06} - {decoded_packet.half} {decoded_packet.pc_mode} {decoded_packet.name} Segment {segment_address}.")
                        # Change state from 'FRAME' to 'SEGMENT'
                        state = 'SEGMENT'

                    # Frame End packet
                    elif decoded_packet.name == 'FRAME_END':
                        # Print
                        if args.debug >= 1: print(f"{bcolors.FRAME}{packet_counter:06} - {decoded_packet.half} {decoded_packet.pc_mode} {decoded_packet.name}: Frame {frame_counter}.{bcolors.ENDC}")
                        # Increment frame counter
                        frame_counter = frame_counter + 1
                        # Restart segments counter
                        segment_counter = [0, 0, 0, 0, 0, 0, 0, 0]
                        # Add the new matrix to frames array
                        frames.append(matrix)
                        # Change state from 'FRAME' to 'IDLE'
                        state = 'IDLE'

                case 'SEGMENT':

                    # Segment End packet
                    if decoded_packet.name == 'SEGMENT_END':

                        if (data_counter != 1792):
                            print(f"{bcolors.ERROR}{packet_counter:06} - ERROR: Data packets counter different than 1792: {data_counter} packets received. {decoded_packet.half} Frame {frame_counter} Segment {segment_address} {bcolors.ENDC}")

                        # Get the address of ended segment
                        segment_address = decoded_packet.segment
                        # Count how many times each segment has been read in a frame
                        segment_counter[segment_address] = segment_counter[segment_address] + 1
                        # Print
                        if args.debug >= 1: print(f"{packet_counter:06} - {decoded_packet.half} {decoded_packet.pc_mode} {decoded_packet.name} Segment {segment_address}.")

                        # Change state from 'SEGMENT' to 'FRAME'
                        state = 'FRAME'
                    
                    # Data packet
                    elif data_counter < 1792:

                        # Calculate x coordinate of data packet
                        if (segment_address < 4): 
                            # Left side of matrix
                            x = 224 - 8*(data_counter % 28) - (8 - 2*int(segment_address))
                        else:
                            # Right side of matrix
                            x = 224 + 8*(data_counter % 28) + (2*int(segment_address) - 8)
    
                        # Calculate y coordinate of data packet
                        y = 4*(data_counter // 28)
    
                        if readout_mode == '8bit':
                            # Copy each byte from packet for corresponding pixel of matrix
                            for pixel in range(4):
                                matrix[y + pixel][x] = decoded_packet.array8bit[7 - 2*pixel]
                                matrix[y + pixel][x + 1] = decoded_packet.array8bit[6 - 2*pixel]
                        
                        elif readout_mode == '16bit':
                            # Copy two bytes from packet for corresponding pixel of matrix
                            for pixel in range(4):
                                if pixel == 0:
                                    matrix[y + pixel][x + segment_counter[segment_address]] = (decoded_packet.array8bit[7] << 8) + decoded_packet.array8bit[5]
                                elif pixel == 2:
                                    matrix[y + pixel][x + segment_counter[segment_address]] = (decoded_packet.array8bit[6] << 8) + decoded_packet.array8bit[4]
                                if pixel == 1:
                                    matrix[y + pixel][x + segment_counter[segment_address]] = (decoded_packet.array8bit[3] << 8) + decoded_packet.array8bit[1]
                                elif pixel == 3:
                                    matrix[y + pixel][x + segment_counter[segment_address]] = (decoded_packet.array8bit[2]<< 8) + decoded_packet.array8bit[0]

                    # Increment data counter
                    data_counter = data_counter + 1

    # Add new frames to matrixes array
    matrixes.append(frames)

    iter_time = (time.time() - loop_time)*1000
    print(f'Decode time {iter_time:.3f} ms. Total frames {frame_counter}. Time per frame: {iter_time/frame_counter:.3f} ms')

# Concatenate botton and top matrixes to construct full images
images = []
for i in range(min(len(matrixes[0]),len(matrixes[1]))):
    images.append(np.concatenate((matrixes[1][i], np.rot90(matrixes[0][i], 2)), axis = 0))

if args.save_file == True:
  print(f'Saving output image image in {args.path} as {args.filename}')
  # Save images in a .hdf5 file
  with h5py.File(os.path.join(args.path,f'{args.filename}.hdf5'), mode = 'w') as hdf5_file:
      hdf5_file.create_dataset('/entry/data/data', data = images)