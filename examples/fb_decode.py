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
import matplotlib.pyplot as plt
import h5py
import struct

##################################################################################################################################################
#INPUT VARIABLES TO BE SCRIPT ARGUMENTS IN THE NEAR FUTURE
##################################################################################################################################################
save_file = True
plot = False
# Get binary file names in path
path = './out_desespero/'
#Debug will print possible control packages inside data
debug = False
##################################################################################################################################################

class bcolors:
    ERROR = '\033[91m'
    ENDC = '\033[0m'
    CONTROL = '\033[92m'
    WARNING = '\033[33m'
    DEBUG = '\033[94m'
    FRAME = "\033[95m"

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

        self.control = True
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
                #set control to False if no decoded name is found
                self.control = False
    
        self.array8bit = struct.unpack('8B', packet)

filenames = sorted(glob.glob(path + '*.dat*')) # SPIDR4 sdaq uses .dat
print(f'Reading files: {filenames}')

# Create a matrixes array to plot
matrixes = []

# For each binary file
for file in filenames:

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
    last_control = 0
    
    # Packet Coordinates (Pixel 0)
    x = 0
    y = 0
    
    # Analyze each packet in the file
    for packet_counter,packet in enumerate(packets):

        decoded_packet = DecodePacket(packet)
        # FSM definition
        match state:

            case 'IDLE':
                # Look for Shutter Rise packet
                if decoded_packet.name == 'SHUTTER_RISE':
                    state = 'WAITING_START'
                    print(f"{bcolors.CONTROL}{packet_counter:06} - {decoded_packet.half} 0x{decoded_packet.header:02X}: {decoded_packet.name}{bcolors.ENDC}")
                # See if a control packet arrived during Idle State
                elif decoded_packet.control == True and debug:
                    print(f"{bcolors.WARNING}{packet_counter:06} - {decoded_packet.half} CONTROL PACKET 0x{decoded_packet.header:02X}: {decoded_packet.name}{bcolors.ENDC}")

            case 'WAITING_START':
                # Look for Frame Start packet
                if decoded_packet.name == 'FRAME_START':
                    readout_mode = decoded_packet.pc_mode
                    matrix = np.zeros((256, 448), dtype=np.uint8 if readout_mode == '8bit' else np.uint16)                                  
                    print(f"{bcolors.FRAME}{packet_counter:06} - {decoded_packet.half} {decoded_packet.pc_mode} {decoded_packet.name}: Frame {frame_counter}. {packet_counter-last_control-1} packets from last control{bcolors.ENDC}")
                    state = 'FRAME'
                    last_control = packet_counter
                elif decoded_packet.name == 'SHUTTER_FALL':
                    print(f"{bcolors.CONTROL}{packet_counter:06} - {decoded_packet.half} 0x{decoded_packet.header:02X}: {decoded_packet.name}{bcolors.ENDC}")
                    state = 'IDLE'
                # See if a control packet arrived during Idle State
                elif decoded_packet.control == True and debug:
                    print(f"{bcolors.WARNING}{packet_counter:06} - {decoded_packet.half} CONTROL PACKET 0x{decoded_packet.header:02X}: {decoded_packet.name}{bcolors.ENDC}")
                
            case 'FRAME': 
                # Look for Segment Start packet
                if decoded_packet.name == 'SEGMENT_START':
                    # Get the address of started segment
                    segment_address = decoded_packet.segment
                    # Start counting data packets read from the next segment
                    data_counter = 0
                    # Print
                    print(f"{packet_counter:06} - {decoded_packet.half} {decoded_packet.pc_mode} {decoded_packet.name} Segment {segment_address}. {packet_counter-last_control-1} packets from last control")
                    # Change state from 'FRAME' to 'SEGMENT'
                    state = 'SEGMENT'
                    last_control = packet_counter
                    
                # Frame End packet
                elif decoded_packet.name == 'FRAME_END':
                    # Print
                    print(f"{bcolors.FRAME}{packet_counter:06} - {decoded_packet.half} {decoded_packet.pc_mode} {decoded_packet.name}: Frame {frame_counter}. {packet_counter-last_control-1} packets from last control{bcolors.ENDC}")
                    # Increment frame counter
                    frame_counter = frame_counter + 1
                    # Restart segments counter
                    segment_counter = [0, 0, 0, 0, 0, 0, 0, 0]
                    # Add the new matrix to frames array
                    frames.append(matrix)
                    # Change state from 'FRAME' to 'IDLE'
                    state = 'WAITING_START'
                    last_control = packet_counter

            case 'SEGMENT':
                    
                # Segment End packet
                if decoded_packet.name == 'SEGMENT_END':

                    if (data_counter != 1792):
                        print(f"{bcolors.ERROR}{packet_counter:06} - ERROR: Data packets counter different than expected. {data_counter} packets. {bcolors.ENDC}")

                    # Get the address of ended segment
                    segment_address = decoded_packet.segment
                    # Count how many times each segment has been read in a frame
                    segment_counter[segment_address] = segment_counter[segment_address] + 1
                    # Print
                    print(f"{packet_counter:06} - {decoded_packet.half} {decoded_packet.pc_mode} {decoded_packet.name} Segment {segment_address}. {packet_counter-last_control-1} packets from last control")

                    # Change state from 'SEGMENT' to 'FRAME'
                    state = 'FRAME'
                    #print(f"Data counter = {data_counter}")
                    last_control = packet_counter
                
                # Data packet                
                else:
                    #Possible Control Packet During Data
                    if decoded_packet.control == True and debug == True:
                        print(f"{bcolors.DEBUG}{packet_counter:06} - {decoded_packet.half} Possible CONTROL PACKET - 0x{decoded_packet.header:02X}: {decoded_packet.name}{bcolors.ENDC}")
                
                    if data_counter < 1792:
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

# Concatenate botton and top matrixes to construct full images
images = []
for i in range(len(frames)):
    images.append(np.concatenate((matrixes[1][i], np.rot90(matrixes[0][i], 2)), axis = 0))

if plot == True:
    image_to_plot = int(input('Choose wich image you want to plot: (-1 to pass)'))

    if image_to_plot >= 0:
        # Plot reconstructed image
        plt.imshow(images[image_to_plot])
        plt.colorbar()

if save_file == True:
  print(f'Saving image as: {path + 'LNLS_images.hdf5'}')
  # Save images in a .hdf5 file
  with h5py.File(os.path.join(path,'LNLS_images.hdf5'), mode = 'w') as hdf5_file:
      hdf5_file.create_dataset('/entry/data/data', data = images)