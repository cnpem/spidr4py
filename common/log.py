#!/usr/bin/env python3

#############################################################################################################
#
#  log.py
#
#  A log class to create and append to a log file the python calls to the board
#
#  Authors:
#   Mauricio Donatti <mauricio.donatti@lnls.br>
#
#  August 2026
#
#############################################################################################################

import os
from datetime import datetime

#Import spidr4py packages
from spidr4 import rpc

class log:
  def __init__(self,spidr_ctrl,log_msg = None):

    self.ctrl = spidr_ctrl
    #get chipboard carrier information
    self.carrier = self.ctrl.GetChipBoardInfo(rpc.EMPTY)
    #get chips information
    chips = self.ctrl.GetPixelChipInfo(rpc.EMPTY)
    #consider a single ASIC connected in position 0
    self.chip = chips.items[0]

    self.dac_settings_token = 'DAC SETTINGS FILE'

    self.log_filepath = os.path.join(os.path.expanduser("~"),'config',f'{self.carrier.serial}',f'{self.chip.chip_id:08x}')

    #Create the dir if it does not exist
    os.makedirs(self.log_filepath, exist_ok=True)

    filename = 'spidr.log'
    self.log_file = os.path.join(self.log_filepath,filename)

    print(f"Log file: {self.log_file}")

    if log_msg:
      self.append_message(log_msg)

  def append_message(self,log_msg):
    with open(self.log_file,'a') as file:
      file.write(f'{datetime.now().strftime("%Y-%m-%d-%Hh%Mm%Ss")} {log_msg}\n')

  def append_dac_settings(self,filepath):
    with open(self.log_file,'a') as file:
      file.write(f'{datetime.now().strftime("%Y-%m-%d-%Hh%Mm%Ss")} {self.dac_settings_token} {filepath}\n')

  def read_last_settings(self):
    with open(self.log_file, 'r') as file:
      lines = file.readlines()
      for line in reversed(lines):
        if self.dac_settings_token in line:
          print(f'Last DAC load: {line[:-1]}')
          break

    dac_settings_file = line.split()[-1]
    #print(f'DEBUG: last dac settings file: {dac_settings_file}')

    return dac_settings_file
