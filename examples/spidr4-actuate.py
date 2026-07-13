from spidr4 import rpc
import helpers

# Set one of SPIDR4's 'actuator' data points;
# without parameters will output a list of available data points plus current values

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=False, args={
        "name": dict(help="Name of the actuator (without name, a list of available actuators is given)", default="", nargs='?'),
        "val": dict(help="Actuator value (float, int, bool or string)", type=str, nargs='?'),
    #   "val": dict(help="Actuator value (integer only, for now)", type=lambda x: int(x,0), default=0, nargs='?'),
    })

    name = ns.name
    val  = ns.val

    # Determine the type of 'val' provided by the user: bool, int, float or string
    if val == "True" or val == "true" or val == "False" or val == "false":
        b_val = (val == "True" or val == "true")
        type = 3
    else:
        try:
            i_val = int(val)
            type = 1
        except ValueError:
            try:
                f_val = float(val)
                type = 2
            except ValueError:
                s_val = val
                type = 4 # i.e. string type

    # Show what was selected
    type_str = ["<none>", "int", "float", "bool", "string", "ulong"] 
    if name != "":
        print( f"Using: name={name}, val={val}, type={type} ({type_str[type]})" )

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the SPIDR4 'peripherals' service
        peripherals = rpc.PeripheralStub(channel)

        if name == "":
            dps = peripherals.GetActuateData(rpc.EMPTY)
            si = sorted(dps.items, key=lambda x : x.id)
            t2f = {
                rpc.INT:     ("{val:d}", lambda x: x.int_value),
                rpc.ULONG:   ("0x{val:X}", lambda x: x.ulong_value),
                rpc.FLOAT:   ("{val:.2f}", lambda x: x.float_value),
                rpc.BOOLEAN: ("{val!s}", lambda x: x.bool_value),
                rpc.STRING:  ("\"{val:s}\"", lambda x: x.string_value)
            }
            print("=> List of available actuator data points:")
            print(f"{'DataPoint ID':<32s} Valid {'Value':>12s}")
            print(f"{'-------------':<32s} ------ {'------':>12s}")
            for dp in si:
                vc = dp.value
                conv = t2f[vc.type]
                valstr = conv[0].format(val=conv[1](vc))
                print(f"{dp.id:<32s} {dp.valid!s:5s} {valstr:>12s}")
        else:
            # Create a datapoints list (of items to 'actuate', in this case just the single selected one)
            datapts = rpc.DataPointList()
            if type == 1:
                datapts.items.append( rpc.DataPoint(id=name, value=rpc.Value(type=1, int_value=i_val)) )
            elif type == 2:
                datapts.items.append( rpc.DataPoint(id=name, value=rpc.Value(type=2, float_value=f_val)) )
            elif type == 3:
                datapts.items.append( rpc.DataPoint(id=name, value=rpc.Value(type=3, bool_value=b_val)) )
            elif type == 4:
                datapts.items.append( rpc.DataPoint(id=name, value=rpc.Value(type=4, string_value=s_val)) )
            elif type == 5:
                datapts.items.append( rpc.DataPoint(id=name, value=rpc.Value(type=5, ulong_value=s_val)) )

            # Execute
            peripherals.ActuateNow(datapts)
            print( "Done" )
