#!/usr/bin/env python3

#############################################################################################################
#
#  tpx4_fb_fast.py
#  
#  Performs frame-based configuration using 10G interface or Optical Fast Linkes (Firefly)
#
#  Authors: 
#   Mauricio Donatti <mauricio.donatti@lnls.br>
#
#  July 2025
#
#############################################################################################################

#Import python libs
import sys
import os
from argparse import BooleanOptionalAction

sys.path.insert(0, os.path.join(os.getcwd(),'..'))

#Import spidr4 packages
from spidr4 import rpc, utils

#Import repository modules and functions
import helpers
from common import dacs

ns = helpers.cl_parse(with_chip_idx=True, args={
    "iface": dict(help="Network interface for Spidr4 10G link", type=str, nargs='?'),
    "--ffly-mode": dict(help="Use firefly links instead of the 10 GbE port", action=BooleanOptionalAction,default=False),
    '--channels-top': dict(type=lambda x: int(x,0),default=0xFF,choices=range(0,256),metavar='[0x00-0xFF]',help='Choose TOP channels to be enabled as hex 8bit'),
    '--channels-bot': dict(type=lambda x: int(x,0),default=0xFF,choices=range(0,256),metavar='[0x00-0xFF]',help='Choose BOTTOM channels to be enabled as hex 8bit'),
    '--link-speed-mbps': dict(type=int,choices=[40,80,160,320,640,1280,2560,5120,10240],default=2560,help='Link Speed in MHz'),
    "--xgbe-port": dict(help="10 GbE port", type=int, default=8192),
    "--crw-time-us": dict(type=int,default=1000000,help='Continuous read-write time in microseconds'),
    '--counter': dict(choices=['8bit','16bit'],default='8bit',help='Frame based counter depth'),
    '--reset': dict(action=BooleanOptionalAction,default=False,help='reset Timepix4 ASIC at the beginning'),
    '--status-packets':dict(action=BooleanOptionalAction,default=False,help='Enables sending output status packets in the data stream (for example, Shutter Rise/Fall)'),
    '--force-T0sync':dict(action=BooleanOptionalAction,default=True,help='Force to send T0Sync, even without reset'),
    '--th_e':dict(type=int,default=0,help='Threshold in e-'),
    '--polarity': dict(choices=['h','e'],default='e',help='Charge collection'),
    '--gain': dict(choices=['low','high'],default='high',help='CSA gain'),
})

if ns.iface == None and ns.ffly_mode == False:
    print("If not using --ffly-mode, the xgbe network interface name is required", file=sys.stderr)
    sys.exit(1)
elif ns.iface != None and ns.ffly_mode == True:
    print("Network interface should not be set when using --ffly-mode", file=sys.stderr)
    sys.exit(1)

def get_link_bw(top = True, check_PLL = False, optimize_PLL = False):

    #get high_BW_en at GWT_CONF register to check 160 or 320 MHz mode
    ans = tpx4.ReadReg(
        rpc.ReadRegRequest(
            idx=0,
            addr=0xC207 if top == True else 0x4207,
        )
    )
    high_bw_en = (int.from_bytes(ans.data) >> 24) & 0b1

    #get speed_div_log2 at PCSTX_CTRL register to check PLL divider
    ans = tpx4.ReadReg(
        rpc.ReadRegRequest(
            idx=0,
            addr=0xCC01 if top == True else 0x4C01,
        )
    )

    speed_div_log_2 = int.from_bytes(ans.data) & 0b1111

    if check_PLL: check_optimal_PLL(top = top, en_print=True)

    if optimize_PLL and not(check_optimal_PLL(top=top)):
        print('Optimizing PLL setting')
        ans = tpx4.WriteReg(
            rpc.WriteRegRequest(
                idx=0,
                addr=0xC208 if top == True else 0x4208,
                #      res_PLL    | icp_PLL   | adj_cp_PLL | adj_vco_PLL| cap_small_PLL | cap_large_PLL | rst_vcntr_vdd_PLL
                data= (0b1110<<27 | 0b111<<24 | 0b1111<<20 | 0b0000<<16 | 0b1111<<12    | 0b0011<<8     | 0x00).to_bytes(4)
            )
        )

    return 5120*(2**(high_bw_en))/(2**(speed_div_log_2))

def check_optimal_PLL(top = True,en_print=False):
    if check_optimal_PLL:
        #get GWT_CONF_PLL register
        ans = tpx4.ReadReg(
            rpc.ReadRegRequest(
                idx=0,
                addr=0xC208 if top == True else 0x4208,
            )
        )
        reg_data = int.from_bytes(ans.data)
        #extract fields
        res_PLL = (reg_data>>27)&0xF
        icp_PLL = (reg_data>>24)&0b111
        adj_cp_PLL = (reg_data>>20)&0xF
        adj_vco_PLL = (reg_data>>16)&0xF
        cap_small_PLL = (reg_data>>12)&0xF
        cap_large_PLL = (reg_data>>8)&0xF
        rst_vcntr_vdd_PLL = (reg_data)&0xFF

        if en_print: print(f'res_PLL={res_PLL:04b}\t icp_PLL={icp_PLL:03b}\t adj_cp_PLL={adj_cp_PLL:04b}\t adj_vco_PLL={adj_vco_PLL:04b}\t cap_small_PLL={cap_small_PLL:04b}\t cap_large_PLL={cap_large_PLL:04b}\t rst_vcntr_vdd_PLL={rst_vcntr_vdd_PLL:08b}')

        if icp_PLL != 7 or adj_cp_PLL != 0xF or cap_small_PLL != 0xF:
            print(f'WARNING: {'Top' if top else 'Bottom'} PLL not optimized. See https://timepix4.web.cern.ch/timepix4/timepix4/ChipOperation/configuration_output_links.html')
            return False
        else:
            return True

if ns.ffly_mode == False:
    iface2find = ns.iface
    xgbe_port = ns.xgbe_port

    # Find network interface information
    # Get network card MAC address and IP address
    xgbe_host_mac, xgbe_host_ip = utils.get_nic_info(iface2find)

    # make-up an 10gbe IP for the spidr4 module, as long as it is not the same as xgbe_host_ip
    xgbe_spidr_ip = utils.inc_ip(xgbe_host_ip)
    print(f'Xgbe TOP port: {xgbe_port}')
    print(f'Xgbe BOT port: {xgbe_port+1}')
    print(f'Spidr4 IP: {xgbe_spidr_ip}')
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
    if ns.reset:
        print('Resetting the pixel chips (load default config)')
        ctrl.ResetPixelChips(rpc.EMPTY)
        #Reset the pixel matrix
        tpx4.PixelMatrixReset(rpc.ChipIndex(idx=helpers.cl_chip_idx()))

    # Configure the output
    # ------------------------------------------------------------------------------------------------------
    if ns.ffly_mode:
        # Use optical links (FireFly) to stream raw Timepix4 data
        datastream.ConfigOptical(rpc.OpticalLinkConfig(
                idx=helpers.cl_chip_idx(),
                channels=(ns.channels_top << 8) | ns.channels_bot,
                link_speed=ns.link_speed_mbps
        ))
    else:
        # Use the 10 Gbps ethernet inteface to stream Timepix4 data
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
    #See https://spidr4.nikhef.nl/docs/html/reference/grpc.html?highlight=tpx4readoutconfig#tpx4analogfrontendmode
    match (ns.gain.lower(),ns.polarity.lower()):
        case (g,p) if g == 'high' and p == 'e':
            afe_mode = rpc.TPX4_AFEM_HIGH_GAIN_ELECTRON_COLLECTION
        case (g,p) if g == 'high' and p == 'h':
            afe_mode = rpc.TPX4_AFEM_HIGH_GAIN_HOLE_COLLECTION
        case (g,p) if g == 'low' and p == 'e':
            afe_mode = rpc.TPX4_AFEM_LOW_GAIN_ELECTRON_COLLECTION
        case (g,p) if g == 'low' and p == 'h':
            afe_mode = rpc.TPX4_AFEM_LOW_GAIN_HOLE_COLLECTION
        case _:
            print(f'Error. Not supported gain {ns.gain}.')
            raise SystemError

    tpx4.ReadoutSetConfig(
        rpc.Tpx4ReadoutConfig(
            idx=helpers.cl_chip_idx(),
            mode=rpc.TPX4_READOUT_FRAME8 if ns.counter == '8bit' else rpc.TPX4_READOUT_FRAME16,
            toa_enable=False,
            analog_frontend_mode=afe_mode,
        )
    )

    #Configure DACs
    # ------------------------------------------------------------------------------------------------------
    dacs = dacs.DACs(tpx4,helpers.cl_chip_idx(),adc_half='TOP',adc='internal',debug=True)

    # Configure threshold in e. Polarity = 0 means electrons collection
    dacs.conf_threshold(THR_e=ns.th_e,debug=True)

    # Configure status monitor configuration
    # ------------------------------------------------------------------------------------------------------
    tpx4.StatusMonSetConfig(
        rpc.Tpx4StatusMonConfig(
            idx=helpers.cl_chip_idx(),
            enable=ns.status_packets,                   #Enable status and monitoring packet generation (output status packets in the data stream)
            heartbeat=False,                            #Enable the heartbeat (periodical status packets)
            heartbeat_shift=0,                          #Heartbeat shift. A heartbeat is send every (1 << heatbeat_shift) * 25 ns.
            global_time_reset=False,                    #Resets the global time on T0-sync
            global_time=False,                          #Enable the glboal time counter in status packets (48bit)
            ctrl_data_test=False,                       #Enable sending constant data-test packets
            signal_select=rpc.TPX4_SIGNAL_SELECT_NONE,  #TPX4_SIGNAL_SELECT_NONE or TPX4_SIGNAL_SELECT_CRW_NEXT_FRAME
        )
    )

    # Configure shutter to Spidr4 trigger system (external to ASIC)
    # ------------------------------------------------------------------------------------------------------
    tpx4.ShutterSetConfig(
        rpc.Tpx4ShutterConfig(
            idx=helpers.cl_chip_idx(),
            mode=rpc.TPX4_SHUTTER_MODE_MANUAL,  #change to TPX4_SHUTTER_MODE_PROG_SINGLE for internal controlled shutter,
            input=rpc.TPX4_SHUTTER_INPUT_PAD,   #change to TPX4_SHUTTER_INPUT_SLOW_CONTROL to trigger internal shutter using SC
        )
    )

    # Configure the output links and optimize PLLs
    # ------------------------------------------------------------------------------------------------------

    link_top = get_link_bw(top = True,check_PLL=False,optimize_PLL=True)
    link_bot = get_link_bw(top = False,check_PLL=False,optimize_PLL=True)

    print(f'Link speed TOP: {link_top} Mbps')
    print(f'Link speed BOT: {link_bot} Mbps')

    #Calculate crw registers needed value:
    if ns.ffly_mode:
        # Get the maximum number of active optical links
        Nlinks = max(bin(ns.channels_top).count('1'), bin(ns.channels_bot).count('1'))
    else:
        # When using the 10 Gbps ethernet interface, only one link per top/bottom is active
        Nlinks = 1

    #Compute register value (crw_regs_val) in order to match desired crw_wait_time for a given speed and links number
    LinkSpeed_Mbps = max(link_top,link_bot)
    clk_datapath_MHz = 160                        #clk_datapath default config
    counter_depth = 8 if ns.counter == '8bit' else 16
    readout_time_frame_us = 256*448*counter_depth/(LinkSpeed_Mbps*Nlinks)
    crw_regs_val = int((ns.crw_time_us - readout_time_frame_us)*clk_datapath_MHz)
    if crw_regs_val <= 0:
        print(f'ERROR: crw wait time to short for {LinkSpeed_Mbps} Mbps link speed. Setting to 1 cycle. {crw_regs_val} cannot be 0 or negative')
        crw_regs_val = 1
    print(f'Readout time per frame: {readout_time_frame_us} us. crw_wait_time register value: {crw_regs_val}')

    #Configure CRW_WAIT_TIME Bottom and Top registers
    for reg in [0xC202,0x4202]:#['CRW_WAIT_TIME_TOP','CRW_WAIT_TIME_BOTTOM']
    
        tpx4.WriteReg(
            rpc.WriteRegRequest(
                idx=0,
                addr=reg,
                data=crw_regs_val.to_bytes(4)
            )
        )

        ans = tpx4.ReadReg(
            rpc.ReadRegRequest(
                idx=0,
                addr=reg,
            )
        )

        print(f'Register {reg:20}: {int.from_bytes(ans.data)} clock cycles, {int.from_bytes(ans.data)/(clk_datapath_MHz*1e6)} seconds')

    #Force T0sync to start readout
    #   It's known that one packet at the first segment will be lost if Tosync status packet is sent
    if ns.reset or ns.force_T0sync:
        tpx4.T0Sync(rpc.ChipIndex(idx=helpers.cl_chip_idx()))
