#
# This example opens all optical channels to generate a PRBS signal.
#
from spidr4 import tpx4tools, rpc
import helpers

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=True)

    # Select PRBS mdoe
    PRBS_MODE = 0x4

    # Select bits for which channels should generate a signal
    CHANNELS_TOP = 0xff
    CHANNELS_BOT = 0xff

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
            channels=( CHANNELS_BOT << 8 ) | CHANNELS_TOP,            # Enable all 16 channels (may also be 0, which means 'all available')
            link_speed=2560          # 2.56 GHz
        ))

        # Configure PRBS (no high-level support though)
        tpx4tools.enable_prbs(tpx4, CHANNELS_TOP, CHANNELS_BOT, PRBS_MODE)
        input("Press enter to stop PRBS>")
        datastream.ConfigNone(rpc.ChipIndex(idx=helpers.cl_chip_idx()))
