from spidr4 import rpc
import helpers

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=False)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the service
        peripherals = rpc.PeripheralStub(channel)

        # Get the devices status and sort by name
        stats = peripherals.GetDeviceStatus(rpc.EMPTY)
        sorted_items = sorted(stats.items, key=lambda x : x.name)

        # No need to display 'disabled': is 'valid' inverted
        #print(f"{'Device name':<24s} {'Part':<12s} Valid   Disabled")
        #print(f"{'-------------':<24s} {'-----':<12s} ------  --------")
        print(f"{'Device name':<24s} {'Part':<12s} Valid   I2C info")
        print(f"{'-------------':<24s} {'-----':<12s} ------  ---------")
        for stat in sorted_items:
            # Display
            if stat.busname == "":
                print(f"{stat.name:<24s} {stat.part!s:12s} {stat.valid!s:<7s}")
            elif stat.busname_mux == "":
                print(f"{stat.name:<24s} {stat.part!s:12s} {stat.valid!s:<7s}"
                      f" (bus={stat.busname}, addr=0x{stat.address:02x})")
            else:
                print(f"{stat.name:<24s} {stat.part!s:12s} {stat.valid!s:<7s}"
                      f" (bus={stat.busname}, addr=0x{stat.address:02X}, "
                      f"mux: {stat.busname_mux},0x{stat.address_mux:02X},chan={stat.mux_channel})")
