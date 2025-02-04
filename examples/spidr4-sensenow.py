from spidr4 import rpc
import helpers

# Get a selected set of sensor readings from a SPIDR4
# (this is just a demo program)

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=False)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the SPIDR4 'peripherals' service
        periph = rpc.PeripheralStub(channel)

        # Compose a list of datapoints to read out
        stringlist = rpc.StringList(items=["carrier/temp/temperature",
                                           "core/temperature",
                                           "board_pressure/pressure",
                                           "firefly0/tx_enabled"
        ])
        # Execute read-out
        datapts = periph.SenseNow(stringlist)

        # And display
        type2format = {
            rpc.BOOLEAN: ("{val!s}", lambda x: x.bool_value),
            rpc.FLOAT:   ("{val:.2f}", lambda x: x.float_value),
            rpc.INT:     ("{val:d}", lambda x: x.int_value)
        }
        for dp in datapts.items:
            vc = dp.value
            conv = type2format[vc.type]
            valstr = conv[0].format(val=conv[1](vc))
            print(f"{dp.id:<32s} {dp.valid!s:5s} {valstr:>15s}")            
