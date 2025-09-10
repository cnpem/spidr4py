#!/usr/bin/env python3

#############################################################################################################
#
#  dacs.py
#  
#  A DAC class to configure Timepix4 DACs
#
#  For more information about Timepix4 DACS see: https://timepix4.web.cern.ch/timepix4/timepix4/ChipDescription/AnalogFrontEnd.html#digital-to-analog-converters
#
#  Authors:
#   Mauricio Donatti <mauricio.donatti@lnls.br>
#
#  July 2025
#
#############################################################################################################

from spidr4 import rpc

LOOP_MAX_ITERATIONS = 100
VOLTAGE_TOLERANCE_8B = 1e-3
VOLTAGE_TOLERANCE_10B = 500e-6

#Create a dac library
#Based on Table 3.2: https://timepix4.web.cern.ch/timepix4/timepix4/ChipDescription/AnalogFrontEnd.html#digital-to-analog-converters
#fb_default is not in the Table, is LNLS choice for frame based operation
#for DAC see Spidr4 api reference: https://spidr4.nikhef.nl/docs/html/reference/grpc.html#tpx4dac
#for DAC_OUT choices see Spidr4 api reference: https://spidr4.nikhef.nl/docs/html/reference/grpc.html#tpx4dacout
dacs_lib = {
  'VBiasIkrum':{
    'bits':8,
    'unit':'A',
    'fast_default':1e-9,
    'lp_default':1e-9,
    'fb_default':50e-9,
    'fullscale':100e-9,
    'DAC':rpc.TPX4_DAC_VBIASIKRUM,
    'DAC_OUT_TOP':rpc.TPX4_OUT_VBIASIKRUM_TOP,
    'DAC_OUT_BOT':rpc.TPX4_OUT_VBIASIKRUM_BOT,
  },
  'VFBK':{
    'bits':8,
    'unit':'V',
    'fast_default':500e-3,
    'lp_default':500e-3,
    'fb_default':500e-3,
    'fullscale':1.2,
    'DAC':rpc.TPX4_DAC_VFBK,
    'DAC_OUT_TOP':rpc.TPX4_OUT_VBFK_TOP,
    'DAC_OUT_BOT':rpc.TPX4_OUT_VBFK_BOT,
  },
  'VThreshold':{
    'bits':14,
    'unit':'V',
    'fast_default':540e-3,
    'lp_default':540e-3,
    'fb_default':500e-3,
    'fullscale':1.2,
    'DAC':rpc.TPX4_DAC_VTHRESHOLD,
    'DAC_OUT_TOP': rpc.TPX4_OUT_VTHRESHOLD_TOP,
    'DAC_OUT_BOT': rpc.TPX4_OUT_VTHRESHOLD_BOT,
  },
}

class DACs:
  def __init__(self,tpx4_stub,chip_index, adc_half='TOP',adc='internal',initialize=True, debug=True):

    self.tpx4 = tpx4_stub
    self.debug = debug
    self.chip_index = chip_index
    #Check adc half matrix validity
    match adc_half.upper():
      case 'BOT':
        self.adc_half = adc_half
      case 'TOP':
        self.adc_half = adc_half
      case _:
        print('WARNING: adc half should be TOP or BOT. Using TOP as default')
        self.adc_half = 'TOP'

    #Check adc type validity
    match adc.lower():
      case 'internal':
        self.adc_external = False
      case 'external':
        self.adc_external = True
      case _:
        print('WARNING: adc should be internal or external. Using internal as default')
        self.adc_external = False

    if self.adc_external == False:
      # We're going to use the internal ADC, configure at 20 MHz with 32768 ADC cycles
      self.tpx4.ConfigAdc(rpc.Tpx4AdcConfig(clock_ref=20000000, nperiods=32*1024))

    readout_config = self.tpx4.ReadoutGetConfig(rpc.ChipIndex(idx=self.chip_index))
    self.hole_polarity = readout_config.polarity
    self.low_gain = readout_config.gain
    #print(f'Polarity: {readout_config.polarity}')
    #print(f'Gain: {readout_config.gain}')

    if initialize == True:
      for dac,data in dacs_lib.items():
        #Set DAC default value
        if debug: print(f'Set DAC {dac} to default value {data['fb_default']:.3G} {data['unit']} ')
        self.setDAC(dac,value=data['fb_default'],debug=self.debug)

  def setDAC(self,dac_name,value,debug=True):
    if dac_name in dacs_lib.keys():
      if dacs_lib[dac_name]['bits'] == 8:
        resolution_V = dacs_lib[dac_name]['fullscale']/(2**(dacs_lib[dac_name]['bits']))
        dac_code = round(value/resolution_V)&0xFF
        # Write DAC value
        self.tpx4.SetDacs(rpc.DacValueList(idx=self.chip_index,items=[rpc.DacValue(dac=dacs_lib[dac_name]['DAC'], value=dac_code)]))
        if debug: print(f'Write DAC {dac_name}: {value:.3g} V. Initial DAC code: 0x{dac_code:02X}')
        feedback = self.readDAC(dac_name,debug=False)

        #Iterate to find best value for voltage DACs
        if dacs_lib[dac_name]['unit'] == 'V':
          loop_counter=0
          delta_dac_code = round((value-feedback)/resolution_V)
          while abs(value - feedback) >= VOLTAGE_TOLERANCE_8B and loop_counter < LOOP_MAX_ITERATIONS and delta_dac_code != 0:
            delta_dac_code = round((value-feedback)/resolution_V)
            dac_code = (dac_code + delta_dac_code)&0xFF
            self.tpx4.SetDacs(rpc.DacValueList(idx=self.chip_index,items=[rpc.DacValue(dac=dacs_lib[dac_name]['DAC'], value=dac_code)]))
            feedback = self.readDAC(dac_name,debug=False)
            loop_counter +=1
          if debug: print(f'Optimized DAC {dac_name} to: {value:.5f} V with {loop_counter} iterations. DAC code: 0x{dac_code:02X} and readback value: {feedback:.5f} ')

      elif dacs_lib[dac_name]['bits'] == 14:

        #fullrange is around 500mV per coarse adjustment
        #resolution is 10 bits
        resolution_V = 500e-3/(2**10)
        #we can choose three coarse regions to work, based on DAC VTHRESHOLD scan analysis, as the first iteration point
        if value <= 400e-3:
          coarse = 0 #from 0 to 500mV
          fine_adj = round(value/resolution_V)
        elif value <= 800e-3:
          coarse = 4 #from 350mV to 850mV
          fine_adj = round((value-350e-3)/resolution_V)
        else:
          coarse = 9 #from 650mV to saturation (1.150V)
          fine_adj = round((value-650e-3)/resolution_V)
        dac_code = coarse << 10 | fine_adj

        # Write DAC value
        self.tpx4.SetDacs(rpc.DacValueList(idx=self.chip_index,items=[rpc.DacValue(dac=dacs_lib[dac_name]['DAC'], value=dac_code)]))
        if debug: print(f'Write DAC {dac_name}: {value:.3g} V. Initial DAC code: 0x{dac_code:04X}')

        #Iterate to find best value for voltage DACs
        if dacs_lib[dac_name]['unit'] == 'V':
          feedback = self.readDAC(dac_name,debug=False)
          loop_counter=0
          delta_dac_code = round((value-feedback)/resolution_V)
          while abs(value - feedback) >= VOLTAGE_TOLERANCE_10B and loop_counter < LOOP_MAX_ITERATIONS and delta_dac_code != 0:
            delta_dac_code = round((value-feedback)/resolution_V)
            fine_adj = (fine_adj + delta_dac_code)&0x3FF
            dac_code = coarse << 10 | fine_adj
            self.tpx4.SetDacs(rpc.DacValueList(idx=self.chip_index,items=[rpc.DacValue(dac=dacs_lib[dac_name]['DAC'], value=dac_code)]))
            feedback = self.readDAC(dac_name,debug=False)
            loop_counter +=1
          if debug: print(f'Optimized DAC {dac_name} to: {value:.5f} V with {loop_counter} iterations. DAC code: 0x{dac_code:04X} and readback value: {feedback:.5f} ')

      else:
        print(f'ERROR: dac {dac_name} with {dacs_lib[dac_name]['bits']} bits need to be implemented')
        raise SystemExit

      #Return last feeedback value
      return feedback
    else:
      print(f'ERROR: dac {dac_name} not in dac list. Cannot write')
      raise SystemExit
  
  def readDAC(self,dac_name,debug=True):
    if dac_name in dacs_lib.keys():
      #Read DAC value
      value = self.tpx4.AdcRead(rpc.Tpx4AdcRequest(idx=self.chip_index, dac_out=dacs_lib[dac_name][f'DAC_OUT_{self.adc_half}'], external=self.adc_external)).value
      if debug: print(f'Read DAC {dac_name}: {value:.5f} V')
      return value
    else:
      print(f'ERROR: dac {dac_name} not in dac list. Cannot read')
      raise SystemExit

  def conf_threshold(self,
                  THR_e=1000,
                  FBK_V=dacs_lib['VFBK']['fb_default'],
                  debug=True):

    # Nominal calculation of gain does not represent the real gain, Timepix4 CSA parasitic capacitance is around 1.7fF
    #Cf_low = 6e-15
    #Cf_high = 3e-15
    #Cf = Cf_low if LOW_GAIN else Cf_high
    # capacitance = (n*q)/V --> gain (V/e) = q/capacitance
    #Gain_Ve = 1.6e-19/Cf
    #We will use the value from Xavi scripts in V/e
    Gain_Ve = 20.5e-6 if self.low_gain else 34.5e-6

    THR_FBK_V=THR_e*Gain_Ve

    rb_fbk = self.setDAC('VFBK',value=FBK_V,debug=debug)

    THR_V = (FBK_V - THR_FBK_V) if self.hole_polarity else (FBK_V + THR_FBK_V)

    rb_th = self.setDAC('VThreshold',value=THR_V,debug=debug)

    meas_threshold_v = (rb_fbk - rb_th) if self.hole_polarity else (rb_th - rb_fbk)
    meas_threshold_e = meas_threshold_v/Gain_Ve

    if debug:
        print(f'Operation threshold target: {THR_e} e. Threshold measured {meas_threshold_e} e')
        print(f'DAC VFBK target {FBK_V:.3f}. Measured {rb_fbk:.3f}')
        print(f'DAC VThreshold target {THR_V:.3f}. Measured {rb_th:.3f}')

    return meas_threshold_e