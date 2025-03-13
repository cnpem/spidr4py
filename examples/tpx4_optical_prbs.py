#
# This example opens all optical channels to generate a PRBS signal.
#
from spidr4 import tpx4tools, rpc
import helpers

#python native modules
from enum import Enum

#Define class with PRBS modes
# For details please see: https://timepix4.web.cern.ch/timepix4/timepix4/ChipDescription/pcstx.html?highlight=ext_prbs_mode#id23
class PRBS(Enum):
    PRBS_7 = 'PRBS_7'
    PRBS_15 = 'PRBS_15'
    PRBS_23 = 'PRBS_23'
    PRBS_31 = 'PRBS_31'
    SQUARE_WAVE = 'SQUARE_WAVE'

    def __str__(self):
        return self.value

    def reg_value(self):
        if self.value == 'PRBS_7':
            return 0b001
        elif self.value == 'PRBS_15':
            return 0b010
        elif self.value == 'PRBS_23':
            return 0b011
        elif self.value == 'PRBS_31':
            return 0b100
        elif self.value == 'SQUARE_WAVE':
            return 0b101
        else:
            return 0b100 #PRBS_31

if __name__ == '__main__':

    #For Tpx4 available speeds, see https://timepix4.web.cern.ch/timepix4/timepix4/ChipDescription/pcstx.html#id21
    available_link_speed = [40,80,160,320,640,1280,2560,5120,10240]

    args={
        '--link-speed-mbps': dict(type=int,choices=available_link_speed,default=2560,help='Link Speed in MHz'),
        '--prbs-mode': dict(type=PRBS,choices=list(PRBS),default='PRBS_31',help='PRBS Mode'),
        '--channels-top': dict(type=lambda x: int(x,0),default=0xFF,choices=range(0,256),metavar='[0x00-0xFF]',help='Choose TOP channels to be enabled as hex 8bit'),
        '--channels-bot': dict(type=lambda x: int(x,0),default=0xFF,choices=range(0,256),metavar='[0x00-0xFF]',help='Choose BOTTOM channels to be enabled as hex 8bit'),
    }

    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=True,args=args)

    # Select PRBS mdoe
    PRBS_MODE = ns.prbs_mode.reg_value()

    # Select bits for which channels should generate a signal
    CHANNELS_TOP = ns.channels_top
    CHANNELS_BOT = ns.channels_bot

    print('-----------------------------------------------------------------------------')
    print(f'Starting PRBS MODE:       {ns.prbs_mode}')
    print(f'Channels Enabled Top:     {ns.channels_top:08b}')
    print(f'Channels Enabled Bottom:  {ns.channels_bot:08b}')
    print(f'Link Speed:               {ns.link_speed_mbps} Mbps')
    print('-----------------------------------------------------------------------------')


    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the services
        # ------------------------------------------------------------------------------------------------------
        control = rpc.ControlInfoStub(channel)
        tpx4 = rpc.Timepix4Stub(channel)
        datastream = rpc.DataStreamStub(channel)

        # Reset the pixel chips (will also load the default configuration)
        # ------------------------------------------------------------------------------------------------------
        control.ResetPixelChips(rpc.EMPTY)

        # Configure the output
        # ------------------------------------------------------------------------------------------------------
        datastream.ConfigOptical(rpc.OpticalLinkConfig(
            idx=helpers.cl_chip_idx(),
            channels=( CHANNELS_BOT << 8 ) | CHANNELS_TOP,            # Enable channels
            link_speed=ns.link_speed_mbps
        ))

        # Configure PRBS (no high-level support though)
        tpx4tools.enable_prbs(tpx4, CHANNELS_TOP, CHANNELS_BOT, PRBS_MODE)
        input("Press enter to stop PRBS>")
        datastream.ConfigNone(rpc.ChipIndex(idx=helpers.cl_chip_idx()))
