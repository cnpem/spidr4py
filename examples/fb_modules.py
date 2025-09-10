#!/usr/bin/env python3

#############################################################################################################
#
#  fb_modules.py
#  
#  Performs frame-based decode and provides modules for other scripts integration
#       The main task is provided to decode Spidr4 SDAQ files
#
#  Authors: 
#   Allan Borgato <allan.borgato@lnls.br>
#   Mauricio Donatti <mauricio.donatti@lnls.br>
#
#  September 2025
#
#############################################################################################################

import numpy as np
import struct
import time

# -----------------------------------------------------------------------------------------------------------
# colormap class to keep prints more readable
class bcolors:
    ERROR = '\033[91m'
    ENDC = '\033[0m'
    CONTROL = '\033[92m'
    WARNING = '\033[33m'
    DEBUG = '\033[94m'
    FRAME = "\033[95m"
    SDAQ = '\033[96m'

# -----------------------------------------------------------------------------------------------------------
# DecodePacket class is responsible to decode each 64-bit packet, find probable control packets and structure the data
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
        self.array8bit = struct.unpack('8B',packet.to_bytes(8))

# -----------------------------------------------------------------------------------------------------------
# Packet2Frame class is responsible receive multiple packets and reconstruct the frames
# The class keeps a state machine decoding and counting received packets
# Parameters:
#   debug: debug level: Increase to be more verbose
#   use_shutter_control_packets: decide if it should look for shutter control packets to signalize valid frames
class Packet2Frame:
    def __init__(self,debug=1,use_shutter_control_packets = True):

        # Create a frames array
        self.frames = []

        # Finite State Machine (FSM)
        self.state = 'IDLE' # IDLE, FRAME_STARTED, SEGMENT_STARTED, etc

        self.debug = debug
        self.use_shutter_control_packets = use_shutter_control_packets

        # Indexes to control FSM
        self.frame_counter = 0
        self.data_counter = 0
        self.packet_counter = 0
        self.segment_counter = [0, 0, 0, 0, 0, 0, 0, 0]
        self.segment_address = 0
        self.shutter_rise = self.shutter_fall = False

    #This method should be called for each packet, in sequence
    def read_packet(self,packet):

        self.packet_counter +=1

        #Decode the current packet
        self.decoded_packet = DecodePacket(packet)

        # Look for Shutter Rise packet
        if self.decoded_packet.name == 'SHUTTER_RISE' and self.state != 'SEGMENT':
            self.shutter_rise = True
            self.shutter_fall = False
            if self.debug >= 1: print(f"{bcolors.CONTROL}{self.packet_counter:06} - {self.decoded_packet.half} 0x{self.decoded_packet.header:02X}: {self.decoded_packet.name}{bcolors.ENDC}")

        # Look for a shutter fall package
        elif self.decoded_packet.name == 'SHUTTER_FALL' and self.state != 'SEGMENT':
            if self.debug >= 1: print(f"{bcolors.CONTROL}{self.packet_counter:06} - {self.decoded_packet.half} 0x{self.decoded_packet.header:02X}: {self.decoded_packet.name}{bcolors.ENDC}")
            self.shutter_fall = True

        # FSM definition
        match self.state:

            case 'IDLE':
                # Look for Frame Start packet
                if self.decoded_packet.name == 'FRAME_START' and (self.shutter_rise or (not self.use_shutter_control_packets)):
                    self.frame_start_t0 = time.time()
                    self.readout_mode = self.decoded_packet.pc_mode
                    self.matrix = np.zeros((256, 448), dtype=np.uint8 if self.readout_mode == '8bit' else np.uint16)
                    if self.debug >= 1: print(f"{bcolors.FRAME}{self.packet_counter:06} - {self.decoded_packet.half} {self.decoded_packet.pc_mode} {self.decoded_packet.name}: Frame {self.frame_counter}.{bcolors.ENDC}")
                    self.state = 'FRAME'
                    #If we received a shutter fall, this one is the last frame
                    if self.shutter_fall == True:
                        self.shutter_rise = False
                # See if a control packet arrived during Idle State
                elif  self.debug >= 2 and self.decoded_packet.control == True:
                    print(f"{bcolors.WARNING}{self.packet_counter:06} - {self.decoded_packet.half} CONTROL PACKET 0x{self.decoded_packet.header:02X}: {self.decoded_packet.name}{bcolors.ENDC}")
                
            case 'FRAME':
                # Look for Segment Start packet
                if self.decoded_packet.name == 'SEGMENT_START':
                    # Get the address of started segment
                    self.segment_address = self.decoded_packet.segment
                    # Start counting data packets read from the next segment
                    self.data_counter = 0
                    if self.debug >= 3: print(f"{self.packet_counter:06} - {self.decoded_packet.half} {self.decoded_packet.pc_mode} {self.decoded_packet.name} Segment {self.segment_address}.")
                    # Change state from 'FRAME' to 'SEGMENT'
                    self.state = 'SEGMENT'

                # Frame End packet
                elif self.decoded_packet.name == 'FRAME_END':
                    # Print
                    if self.debug >= 1: print(f"{bcolors.FRAME}{self.packet_counter:06} - {self.decoded_packet.half} {self.decoded_packet.pc_mode} {self.decoded_packet.name}: Frame {self.frame_counter} time {1000*(time.time() - self.frame_start_t0):.3f} ms.{bcolors.ENDC}")
                    # Increment frame counter
                    self.frame_counter +=1
                    # Restart segments counter
                    self.segment_counter = [0, 0, 0, 0, 0, 0, 0, 0]
                    # Add the new matrix to frames array
                    self.frames.append(self.matrix)
                    # Change state from 'FRAME' to 'IDLE'
                    self.state = 'IDLE'

            case 'SEGMENT':

                # Segment End packet
                if self.decoded_packet.name == 'SEGMENT_END':

                    if (self.data_counter != 1792):
                        print(f"{bcolors.ERROR}{self.packet_counter:06} - ERROR: Data packets counter different than 1792: {self.data_counter} packets received. {self.decoded_packet.half} Frame {self.frame_counter} Segment {self.segment_address} {bcolors.ENDC}")

                    # Get the address of ended segment
                    self.segment_address = self.decoded_packet.segment
                    # Count how many times each segment has been read in a frame
                    self.segment_counter[self.segment_address] += 1
                    # Print
                    if self.debug >= 3: print(f"{self.packet_counter:06} - {self.decoded_packet.half} {self.decoded_packet.pc_mode} {self.decoded_packet.name} Segment {self.segment_address}.")

                    # Change state from 'SEGMENT' to 'FRAME'
                    self.state = 'FRAME'
                
                # Data packet - 
                elif self.data_counter < 1792:

                    # Calculate x coordinate of data packet
                    if (self.segment_address < 4): 
                        # Left side of matrix
                        x = 224 - 8*(self.data_counter % 28) - (8 - 2*int(self.segment_address))
                    else:
                        # Right side of matrix
                        x = 224 + 8*(self.data_counter % 28) + (2*int(self.segment_address) - 8)

                    # Calculate y coordinate of data packet
                    y = 4*(self.data_counter // 28)

                    if self.readout_mode == '8bit':
                        # Copy each byte from packet for corresponding pixel of matrix
                        for pixel in range(4):
                            self.matrix[y + pixel][x] = self.decoded_packet.array8bit[2*pixel]
                            self.matrix[y + pixel][x + 1] = self.decoded_packet.array8bit[2*pixel+1]
                    
                    elif self.readout_mode == '16bit':
                        # Copy two bytes from packet for corresponding pixel of matrix
                        for pixel,msb,lsb in zip([0,2,1,3],[0,1,4,5],[2,3,6,7]):
                            self.matrix[y + pixel][x + self.segment_counter[self.segment_address]] = (self.decoded_packet.array8bit[msb] << 8) + self.decoded_packet.array8bit[lsb]

                # Increment data counter
                self.data_counter += 1

# -----------------------------------------------------------------------------------------------------------
# This module can be called as main to decode SDAQ Spidr4 files
if __name__=="__main__":

    import glob
    import os
    import h5py
    import argparse
    import pickle
    
    def dir_path(path):
        if os.path.isdir(path):
            return path
        else:
            raise argparse.ArgumentTypeError(f"readable_dir:{path} is not a valid path")

    #create a parser to properly parse script arguments
    parser = argparse.ArgumentParser(
        prog='fb_modules.py',
        description='performs a Timepix4 frame based decode from SDAQ saved files',
        epilog='This script interprets frame based data and save image files',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('--path',type=dir_path,required=True,help='path to input and output file')
    parser.add_argument('--save-file',action=argparse.BooleanOptionalAction,default=True,help='save hdf5 output file')
    parser.add_argument('--shutter-control-packets',action=argparse.BooleanOptionalAction,default=False,help='use shutter rise/fall to compose valid frames')
    parser.add_argument('--filename',type=str,default='decoded',help='test name to be appended to output filename')
    parser.add_argument('--debug',type=int,choices=range(4),default=1,help='Print debug level. 0: no print, 1: standard, 2: verbose, 3: all messages')

    args = parser.parse_args()

    filenames = sorted(glob.glob(os.path.join(args.path,'*.dat*'))) # SPIDR4 sdaq uses .dat
    print(f'Reading files: {filenames}')

    # For each binary file
    for file in filenames:

        print('------------------------------------------------------------------------------------------------------------------------------------------------------------------------------')
        # Show wich file is being read
        print(f"Decoding File: {file}")
 
        # Open file to store packets array
        packets = np.fromfile(file, dtype=np.uint64)

        # Create a new decoder
        decoder = Packet2Frame(debug=args.debug,use_shutter_control_packets=args.shutter_control_packets) 

        # Compute loop time
        loop_time = time.time()

        # We need to check for Spidr4 valid frames
        #See https://spidr4.nikhef.nl/docs/html/software/dataformat.html
        spidr_valid_frame = False

        # Analyze each packet in the file
        for packet_counter,packet in enumerate(packets):

            #Filter spidr4 headers to consider only 'Pixel Data' groups
            if spidr_valid_frame == False and ((packet>>48 & 0xFFFF) in [0x0002,0x0020,0x0021,0x0022,0x0030,0x0031,0x0032]):
                spidr_valid_frame = True
                spidr_frame_counter = 0
                spidr_content_size = packet & 0xFFFFFFFF
                if args.debug >= 2: print(f'{bcolors.SDAQ}{packet_counter:06} - Spidr4 frame header packet: 0x{packet:016X}. Content size: {spidr_content_size} packets{bcolors.ENDC}')

            elif spidr_valid_frame == True:
                #Increment spidr frame counter and check if the current packet is the spidr frame end
                spidr_frame_counter+=1
                if spidr_frame_counter == spidr_content_size:
                    spidr_valid_frame = False
                    if args.debug >= 2: print(f'{bcolors.SDAQ}{packet_counter:06} - Spidr4 last frame packet. Counter {spidr_frame_counter}. Content size: {spidr_content_size} packets{bcolors.ENDC}')

                decoder.read_packet(int(packet))

        if decoder.frame_counter > 0:
            #Compute file decode time
            iter_time = (time.time() - loop_time)*1000
            print(f'Decode time {iter_time:.3f} ms. Total frames {decoder.frame_counter}. Time per frame: {iter_time/decoder.frame_counter:.3f} ms')
        else:
            print('No frames found!')

        #Save hdf5 files
        if args.save_file == True:
            output_filename = f'{file[:-4]}_{args.filename}.hdf5'
            print(f'Saving output image image in {args.path} as {output_filename}')
            # Save images in a .hdf5 file
            with h5py.File(os.path.join(output_filename), mode = 'w') as hdf5_file:
                hdf5_file.create_dataset('/entry/data/data', data = decoder.frames)