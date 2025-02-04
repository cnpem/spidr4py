#
# Example shows how to enable the digital pixel for the first two columns,
# both bottom and top using low level register access.
#
from spidr4 import tpx4tools, rpc, tpx4regs
import helpers

def bit_reverse(value, bits):
    return sum(1 << (bits-1-i) for i in range(bits) if value>>i&1)

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=True)


    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the services
        # ------------------------------------------------------------------------------------------------------
        control = rpc.ControlInfoStub(channel)
        tpx4 = rpc.Timepix4Stub(channel)

        # Reset the pixel chips (will also load the default configuration)
        # ------------------------------------------------------------------------------------------------------
        control.ResetPixelChips(rpc.EMPTY)

        # Create 16 super-pixel configurations. Only first SP lowest bit is set to 0. 
        sp_config_regs = [0x000001] + [0x000000] * 15
        
        # Convert to bytes (Big-endian)
        sp_config = []
        for reg_val in sp_config_regs:
            reg_val = bit_reverse(reg_val, 24)
            # Reverse teh bits, as the register is somehow reversed.
            sp_config += [(reg_val >> 16) & 0xff, (reg_val >> 8) & 0xff, reg_val & 0xff]
        sp_config = bytes(sp_config)
        
        # Write first two top using count
        tpx4.WriteReg(
            rpc.WriteRegRequest(
                idx=0,
                addr=tpx4regs.SP_TOP,
                count=2,
                stride=1,
                data=sp_config + sp_config   # Append two, this is not a broadcast
            )
        )
        
        # Write bottom two using two write ops        
        tpx4.WriteReg(
            rpc.WriteRegRequest(
                idx=0,
                addr=tpx4regs.SP_BOT,
                data=sp_config
            )
        )
        
        tpx4.WriteReg(
            rpc.WriteRegRequest(
                idx=0,
                addr=tpx4regs.SP_BOT + 1,
                data=sp_config
            )
        )
