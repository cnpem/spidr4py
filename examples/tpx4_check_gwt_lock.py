#!/usr/bin/env python3

#############################################################################################################
#
#  tpx4_check_gwt_lock.py
#  
#  Check timepix4 GWT lock status
#  see: https://timepix4.web.cern.ch/timepix4/timepix4/ChipDescription/monitoring_and_debugging.html?highlight=snapshot#gwt-pll-and-dll-snapshot 
#
#  Authors: 
#   Mauricio Donatti <mauricio.donatti@lnls.br>
#
#  October 2025
#
#############################################################################################################

from spidr4 import rpc, tpx4tools
import helpers
import time
import datetime

#gwt latches registers [TOP,BOT]
gwt_snapshot_regs = [0xCD22,0x4D22]

#peripheral command registers [TOP,BOT]
per_command_regs = [0xCD20,0x4D20]

#the command to send to peripheral command regs to reset lock latches
SNAPSHOT_CMD = 0x3 #4bits

def reset_latches(tpx4,i):
    half = 'TOP' if i == 0 else 'BOT'
    print(f'{datetime.datetime.now().strftime("%Y-%m-%d_%Hh%Mm%Ss")} - Reset latches {half}')
    tpx4.SimpleWrite(rpc.SimpleWriteRequest(idx=helpers.cl_chip_idx(), addr=per_command_regs[i],val=SNAPSHOT_CMD))

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=True)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:

        # Get the timepix4 service
        tpx4 = rpc.Timepix4Stub(channel)
        reset_latches(tpx4,0)
        reset_latches(tpx4,1)
        print_line = False

        default = []
        for i in range(2):
            default.append(tpx4.SimpleRead(rpc.SimpleReadRequest(idx=helpers.cl_chip_idx(), addr=gwt_snapshot_regs[i])).val)
        while True:
            data_store = []
            for i in range(2):
                half = 'TOP' if i == 0 else 'BOT'
                data = tpx4.SimpleRead(
                    rpc.SimpleReadRequest(idx=helpers.cl_chip_idx(), addr=gwt_snapshot_regs[i])).val
                data_store.append(data)
                if data != default[i]:
                    if print_line == True:
                        print()
                        print_line = False
                    print(f'{datetime.datetime.now().strftime("%Y-%m-%d_%Hh%Mm%Ss")} - {half} lock loss: {data:#018b}. Expected {default[i]:#018b}')
                    reset_latches(tpx4,i)            
            print_line = True
            print(f"\r{datetime.datetime.now().strftime("%Y-%m-%d_%Hh%Mm%Ss")} - TOP latches: {data_store[0]:#018b} BOT latches {data_store[1]:#018b}",end='')
            time.sleep(1)
