from spidr4 import rpc
import helpers

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=False)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the service
        peripherals = rpc.PeripheralStub(channel)

        # Get the datapoints and sort
        dps = peripherals.GetActuateData(rpc.EMPTY)
        si = sorted(dps.items, key=lambda x : x.id)

        t2f = {
            rpc.INT:     ("{val:d}", lambda x: x.int_value),
            rpc.ULONG:   ("0x{val:X}", lambda x: x.ulong_value),
            rpc.FLOAT:   ("{val:.2f}", lambda x: x.float_value),
            rpc.BOOLEAN: ("{val!s}", lambda x: x.bool_value),
            rpc.STRING:  ("\"{val:s}\"", lambda x: x.string_value)
        }
        print(f"{'DataPoint ID':<34s} Valid {'Value':>12s}  [Units]")
        print(f"{'-------------':<34s} ------ {'------':>12s} --------")
        for dp in si:
            # Get this datapoint's units from its 'metadata'
            stringlist = rpc.StringList(items=[dp.id])
            md = peripherals.GetMetaData(stringlist)
            units = md.items[0].unit

            # Value
            vc = dp.value
            conv = t2f[vc.type]
            valstr = conv[0].format(val=conv[1](vc))

            # Display
            if units == "":
                print(f"{dp.id:<34s} {dp.valid!s:5s} {valstr:>12s}")
            else:
                print(f"{dp.id:<34s} {dp.valid!s:5s} {valstr:>12s}  [{units}]")
