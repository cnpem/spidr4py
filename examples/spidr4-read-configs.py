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
        dps = peripherals.GetConfigData(rpc.EMPTY)
        sorted_items = sorted(dps.items, key=lambda x : x.id)

        # Get the datapoints' units from their metadata
        strlist = rpc.StringList( items=[dp.id for dp in sorted_items] )
        metadata = peripherals.GetMetaData( strlist )

        t2f = {
            rpc.BOOLEAN: ("{val!s}", lambda x: x.bool_value),
            rpc.FLOAT:   ("{val:.2f}", lambda x: x.float_value),
            rpc.INT:     ("{val:d}", lambda x: x.int_value),
            rpc.STRING:  ("\"{val:s}\"", lambda x: x.string_value)
        }
        print(f"{'DataPoint ID':<34s} Valid {'Value':>12s}  [Units]")
        print(f"{'-------------':<34s} ------ {'------':>12s} --------")
        index = 0
        for dpoint in sorted_items:
            # Units (if any)
            units = metadata.items[index].unit
            index = index + 1

            # Value
            vc = dpoint.value
            conv = t2f[vc.type]
            valstr = conv[0].format(val=conv[1](vc))

            # Display
            if units == "":
                print(f"{dpoint.id:<34s} {dpoint.valid!s:5s} {valstr:>12s}")
            else:
                print(f"{dpoint.id:<34s} {dpoint.valid!s:5s} {valstr:>12s}  [{units}]")
