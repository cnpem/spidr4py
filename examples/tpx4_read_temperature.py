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
import datetime
import time
import numpy as np

# Computes temperature convertion equation based on sense and bandgap DACs
# For more details, please take a look at https://timepix4.web.cern.ch/timepix4/timepix4/ChipDescription/analog_periphery.html?highlight=temperature#bandgap-and-temperature-sensor
def dacs_to_temperature(sense,bandgap):
    return 330.7-529.6*(sense-bandgap)

if __name__ == '__main__':

    args={
        '--number': dict(type=int,default=1,help='Number of acquisitions'),
        '--save-data': dict(action=BooleanOptionalAction,default=True,help='save data as txt'),
        '--test_name': dict(type=str,default='tpx4_read_temperature',help='test name to be appended to output filenames. Run datetime will always precede the name'),
        '--plot': dict(action=BooleanOptionalAction,default=True,help='control plot show'),
        '--save-plot': dict(action=BooleanOptionalAction,default=False,help='control plot save as figure'),
    }

    date = datetime.datetime.now().strftime("%Y-%m-%d-%Hh%Mm%Ss")

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

        # Resulting found values
        internal_temperature = []
        external_temperature = []

        #get time before start measurements
        t0 = time.time_ns()

        for i in range(ns.number):

            #Read TEMP=SENSE and BANDGAP using internal ADC and compute temperature
            internal_temperature.append(dacs_to_temperature(
                tpx4.AdcRead(rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=DAC_TEMP)).value,
                tpx4.AdcRead(rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=DAC_BANDGAP)).value))

            #Read TEMP=SENSE and BANDGAP using external ADC and compute temperature
            external_temperature.append(dacs_to_temperature(
                tpx4.AdcRead(rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=DAC_TEMP, external=True)).value,
                tpx4.AdcRead(rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=DAC_BANDGAP, external=True)).value))

        #Calculate elapsed time
        delta_t=time.time_ns()-t0

        print("---------------------------------")
        print(f'Read temperature - {ns.number} measurements')
        print(f'Total elapsed time: {delta_t/1e9:.3f} s')
        print(f'Mean time per sample: {delta_t/1e6/ns.number:.3f} ms')
        print("---------------------------------")
        print("Internal ADC Temperature")
        print(f'Mean value: {np.mean(internal_temperature):.2f} °C')
        print(f'Standard deviation: {np.std(internal_temperature):.3e} °C')
        print("---------------------------------")
        print("External ADC Temperature")
        print(f'Mean value: {np.mean(external_temperature):.2f} °C')
        print(f'Standard deviation: {np.std(external_temperature):.3e} °C')
        print("---------------------------------")

        #save txt with measurement data
        if ns.save_data:
            np.savetxt(f'{date}_{ns.test_name}.txt', np.column_stack((internal_temperature,external_temperature)), header='internal,external', delimiter=',', fmt="%.4f")

        plt.figure()
        plt.plot(range(ns.number),internal_temperature,'b*-',label='internal ADC')
        plt.plot(range(ns.number),external_temperature,'r*-',label='external ADC')
        plt.grid()
        plt.legend()
        plt.xlabel('Measurement Index')
        plt.ylabel('Temperature (°C)')
        plt.title('Temperature Measurement')
        plt.tight_layout()
        if ns.save_plot:
            plt.savefig(f'{date}_{ns.test_name}.png', format='png',dpi=500)
        if ns.plot:
            plt.show()
