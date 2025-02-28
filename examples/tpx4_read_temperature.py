from spidr4 import rpc
from argparse import BooleanOptionalAction

try:
    import matplotlib.pyplot as plt
except ImportError:
    import sys
    print("matplotlib is required for this example", file=sys.stderr)
    sys.exit(1)
import sys
import helpers

# Computes temperature convertion equation based on sense and bandgap DACs
# For more details, please take a look at https://timepix4.web.cern.ch/timepix4/timepix4/ChipDescription/analog_periphery.html?highlight=temperature#bandgap-and-temperature-sensor
def dacs_to_temperature(sense,bandgap):
    return 330.7-529.6*(sense-bandgap)

if __name__ == '__main__':

    args={
        '--number': dict(type=int,default=1,help='Number of acquisitions'),
        '--save-txt': dict(action=BooleanOptionalAction,default=True,help='save data as txt'),
        '--test_name': dict(type=str,default='tpx4_read_temperature',help='test name to be appended to output filename'),
        '--plot': dict(action=BooleanOptionalAction,default=True,help='control plot show'),
        '--save-plot': dict(action=BooleanOptionalAction,default=False,help='control plot save as figure'),
    }

    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=True,args=args)

    # DAC configuration
    DAC_TEMP = rpc.TPX4_OUT_TEMP_SENSE
    DAC_BANDGAP = rpc.TPX4_OUT_VBANDGAP_100MV_AT_RES
    
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

        sys.stdout.write(".")
        sys.stdout.flush()

        # Read internal ADC
        internal_dac_values.append(tpx4.AdcRead(
            rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=DAC_TEMP)).value)
        
        # Read internal ADC
        internal_dac_values.append(tpx4.AdcRead(
            rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=DAC_BANDGAP)).value)
        
        TEMP_internal=dacs_to_temperature(internal_dac_values[0],internal_dac_values[1])
        
        # Read external ADC
        external_dac_values.append(tpx4.AdcRead(
            rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=DAC_TEMP, external=True)).value)
        
        # Read external ADC
        external_dac_values.append(tpx4.AdcRead(
            rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=DAC_BANDGAP, external=True)).value)

        TEMP_external=dacs_to_temperature(external_dac_values[0],external_dac_values[1])

        sys.stdout.write("\n")
        sys.stdout.flush()
        # Reset all DACs
        tpx4.SetDacs(dacs)

        print("Internal read")
        print(internal_dac_values)
        print("Temperature[°C] = ",TEMP_internal)
        print("---------------------------------")
        print("External read")
        print(external_dac_values)
        print("Temperature[°C] = ",TEMP_external)