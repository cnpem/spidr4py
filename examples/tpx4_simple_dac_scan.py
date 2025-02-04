from spidr4 import rpc
try:
    import matplotlib.pyplot as plt
except ImportError:
    import sys
    print("matplotlib is required for this example", file=sys.stderr)
    sys.exit(1)
import sys
import helpers

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=True)

    # DAC scan configuration
    DAC = rpc.TPX4_DAC_VBIASIKRUM
    DAC_OUT = rpc.TPX4_OUT_VBIASIKRUM_TOP
    TITLE = "Vbias_IKRUM"
    DAC_SCAN_RANGE = range(0, 256, 3)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # We'll assume Timepix 4 is located at index 0
        tpx4 = rpc.Timepix4Stub(channel)
        # We're going to use the internal ADC, configure at 20 MHz with 8192 ADC cycles
        tpx4.ConfigAdc(rpc.Tpx4AdcConfig(clock_ref=625000, nperiods=16*1024))
        # Copy all DAC values, to reset later on
        dacs = tpx4.GetDacs(rpc.EMPTY)
        # Resulting found values
        internal_dac_values = []
        external_dac_values = []
        for dac_code in DAC_SCAN_RANGE:
            sys.stdout.write(".")
            sys.stdout.flush()
            # Write DAC value
            tpx4.SetDacs(rpc.DacValueList(idx=helpers.cl_chip_idx(),
                items=[rpc.DacValue(dac=DAC, value=dac_code)]))
            # Read internal ADC
            internal_dac_values.append(tpx4.AdcRead(
                rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=DAC_OUT)).value)
            # Read external ADC
            external_dac_values.append(tpx4.AdcRead(
                rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=DAC_OUT, external=True)).value)
        sys.stdout.write("\n")
        sys.stdout.flush()
        # Reset all DACs
        tpx4.SetDacs(dacs)

        # plot!
        plt.title(TITLE)
        plt.plot(DAC_SCAN_RANGE, internal_dac_values, label="Internal")
        plt.plot(DAC_SCAN_RANGE, external_dac_values, label="External")
        plt.xlabel("DAC code")
        plt.ylabel("DAC value [V]")
        plt.legend()
        helpers.save_or_show(plt)

