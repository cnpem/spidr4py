from spidr4 import rpc
import helpers

# Set a SPIDR4's FireFly TX enable (actually: disable) mask,
# on either both FireFly modules (default) or only on #0 or #1

if __name__ == '__main__':
    # Parse command-line (with auto-base detect for 'val')
    ns = helpers.cl_parse(with_chip_idx=False, args={
        "val": dict(help="FireFly TX enable mask value [0x000-0xFFF]", type=lambda x: int(x,0), default=0),
        "-ff0": dict(help="Select FireFly #0", action='store_true'),
        "-ff1": dict(help="Select FireFly #1", action='store_true')
    })

    val = ns.val ^ 0xFFF # The register has bits to disable TX channels
    ff0 = ns.ff0
    ff1 = ns.ff1
    #print( f"val={hex(val)}" )

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the SPIDR4 'peripherals' service
        periph = rpc.PeripheralStub(channel)

        # Compose a datapoints list (of items to 'actuate')
        #datapts = rpc.DataPointList(items=[rpc.DataPoint(id="firefly0/tx_disable",
        #                                                 value=rpc.Value(type=1,int_value=val)),
        #                                   rpc.DataPoint(id="firefly1/tx_disable",
        #                                                 value=rpc.Value(type=1,int_value=val))])

        # Either FireFly 0 or 1, or both (default)
        datapts = rpc.DataPointList()
        if not(ff0 or ff1) or ff0:
            print( "Apply to FireFly #0" )
            datapts.items.append( rpc.DataPoint(id="firefly0/tx_disable",
                                                value=rpc.Value(type=1,int_value=val)) )
        if not(ff0 or ff1) or ff1:
            print( "Apply to FireFly #1" )
            datapts.items.append( rpc.DataPoint(id="firefly1/tx_disable",
                                                value=rpc.Value(type=1,int_value=val)) )
        # Execute
        periph.ActuateNow(datapts)
        print( "Done" )
