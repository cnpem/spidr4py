from spidr4 import rpc
try:
    import matplotlib.pyplot as plt
except ImportError:
    import sys
    print("matplotlib is required for this example", file=sys.stderr)
    sys.exit(1)
import sys
import helpers
import numpy as np

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=True)

    dacs = {
        'BANDGAP':{
            'DAC':rpc.TPX4_DAC_VTHRESHOLD,
            'DAC_OUT':rpc.TPX4_OUT_VBANDGAP_100MV_AT_RES,
            'n_bits': 8,
        },
        'VFBK':{
            'DAC':rpc.TPX4_DAC_VFBK,
            'DAC_OUT':rpc.TPX4_OUT_VBFK_TOP,
            'n_bits': 8,
        },
        'VTHRESHOLD':{
            'DAC':rpc.TPX4_DAC_VTHRESHOLD,
            'DAC_OUT': rpc.TPX4_OUT_VTHRESHOLD_TOP,
            'n_bits': 14,
        },
    }

    with helpers.cl_connect() as channel:
        # We'll assume Timepix 4 is located at index 0
        tpx4 = rpc.Timepix4Stub(channel)
        # We're going to use the internal ADC, configure at 20 MHz with 8192 ADC cycles
        tpx4.ConfigAdc(rpc.Tpx4AdcConfig(clock_ref=625000, nperiods=16*1024))
        # Copy all DAC values, to reset later on
        dacs_bkp = tpx4.GetDacs(rpc.EMPTY)

        for dac in dacs.keys():
            print(f'Scanning DAC {dac}')
            # Resulting found values
            #8-bit DACs
            #14-bit DACs are 10 bits fine adjustments with 4 gain bits. See: https://timepix4.web.cern.ch/timepix4/timepix4/ChipDescription/analog_periphery.html#bits-voltage-dacs
            dacs[dac]['scan_n'] = 8 if dacs[dac]['n_bits'] == 8 else 10
            dacs[dac]['scan_coarse'] = range(2**4-1) if dacs[dac]['n_bits'] == 14 else range(1) 
            dacs[dac]['range'] = np.linspace(0,2**dacs[dac]['scan_n']-1,20,dtype=int)
            dacs[dac]['internal'] = []
            dacs[dac]['external'] = []
            for coarse in dacs[dac]['scan_coarse']:
                sys.stdout.write(f'{coarse:02d}')
                dacs[dac]['internal'].append([])
                dacs[dac]['external'].append([])
                for dac_fine in dacs[dac]['range']:
                    sys.stdout.write(".")
                    sys.stdout.flush()
                    dac_code = dac_fine if dacs[dac]['n_bits'] == 8 else (dac_fine | (coarse << 10))
                    # Write DAC value
                    tpx4.SetDacs(rpc.DacValueList(idx=helpers.cl_chip_idx(),
                        items=[rpc.DacValue(dac=dacs[dac]['DAC'], value=dac_code)]))
                    # Read internal ADC
                    dacs[dac]['internal'][coarse].append(tpx4.AdcRead(
                        rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=dacs[dac]['DAC_OUT'])).value)
                    # Read external ADC
                    dacs[dac]['external'][coarse].append(tpx4.AdcRead(
                        rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=dacs[dac]['DAC_OUT'], external=True)).value)
                sys.stdout.write("\n")
                sys.stdout.flush()

            # plot!
            plt.title(f'DAC {dac} scan')
            for coarse in dacs[dac]['scan_coarse']:
                plt.plot(dacs[dac]['range'], dacs[dac]['internal'][coarse],'--', label=f"Int Coarse {coarse}" if dacs[dac]['n_bits'] == 14 else 'Internal ADC')
                plt.plot(dacs[dac]['range'], dacs[dac]['external'][coarse],'-', label=f"Ext Coarse {coarse}" if  dacs[dac]['n_bits'] == 14 else 'External ADC')
            plt.xlabel("DAC code")
            plt.ylabel("DAC value [V]")
            plt.grid()
            plt.legend(bbox_to_anchor=(1.04, 0.5), loc="center left", borderaxespad=0,fontsize='small',ncols = 2 if dacs[dac]['n_bits'] == 14 else 1)
            plt.tight_layout()
            helpers.save_or_show(plt)

        # Reset all DACs
        tpx4.SetDacs(dacs_bkp)

