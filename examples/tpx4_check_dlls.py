from spidr4 import rpc, tpx4tools
import helpers

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=True)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:

        # Get the timepix4 service
        tpx4 = rpc.Timepix4Stub(channel)

        # Get the spidr4 control service
        ctrl = rpc.ControlInfoStub(channel)

        # Reset all attached pixel chips
        ctrl.ResetPixelChips(rpc.EMPTY)

        # For each EOC, get the lock state by directly accessing the Timepix4 register
        for n in range(0, 112):
            # Bottom EoC
            eoc_bot = tpx4.SimpleRead(
                rpc.SimpleReadRequest(idx=helpers.cl_chip_idx(), addr=0x8100 + n)
            ).val

            # Top EoC
            eoc_top = tpx4.SimpleRead(
                rpc.SimpleReadRequest(idx=helpers.cl_chip_idx(), addr=0x8200 + n)
            ).val

            # Decode the state and print
            top_code, top_lock = tpx4tools.decode_eoc_mon(eoc_top)
            bot_code, bot_lock = tpx4tools.decode_eoc_mon(eoc_bot)

            print(f"Column {n:3d} | top lock={str(top_lock):5s},"
                  f"code={top_code:2d} | lock={str(top_lock):5s}, code={top_code:2d}")

