from spidr4 import rpc, mpx4regs
import helpers

if __name__ == '__main__':
    ns = helpers.cl_parse(with_chip_idx=True)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the medipix4 service
        mpx4 = rpc.Medipix4Stub(channel)

        # Get the spidr4 control service
        ctrl = rpc.ControlInfoStub(channel)

        # Reset all attached pixel chips
        ctrl.ResetPixelChips(rpc.EMPTY)

        bot_id = mpx4.SimpleRead(rpc.SimpleReadRequest(idx=helpers.cl_chip_idx(), addr=mpx4regs.CHIP_ID_BOT)).val
        top_id = mpx4.SimpleRead(rpc.SimpleReadRequest(idx=helpers.cl_chip_idx(), addr=mpx4regs.CHIP_ID_TOP)).val
        print(f"Bottom ID={bot_id:08x}, Top ID={bot_id:08x}")
