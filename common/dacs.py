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
import sys

LOOP_MAX_ITERATIONS = 200

#Create a dac library
#Based on Table 3.2: https://timepix4.web.cern.ch/timepix4/timepix4/ChipDescription/AnalogFrontEnd.html#digital-to-analog-converters
#fb_default is not in the Table, is LNLS choice for frame based operation
#for DAC see Spidr4 api reference: https://spidr4.nikhef.nl/docs/html/reference/grpc.html#tpx4dac
#for DAC_OUT choices see Spidr4 api reference: https://spidr4.nikhef.nl/docs/html/reference/grpc.html#tpx4dacout
dacs_lib = {
  'VBiasPreamp':{
    'bits':8,
    'unit':'A',
    'xavi_default':438e-9,
    'fast_default':728e-9,
    'lp_default':100e-9,
    'fb_default':100e-9,
    'fullscale':1.45e-6,
    'DAC':rpc.TPX4_DAC_VBIASPREAMP,
    'DAC_OUT_TOP': rpc.TPX4_OUT_VBIASPREAMP_TOP,
    'DAC_OUT_BOT': rpc.TPX4_OUT_VBIASPREAMP_BOT,
  },
  'VCascPreamp':{
    'bits':8,
    'unit':'V',
    'xavi_default':750e-3,
    'fast_default':750e-3,
    'lp_default':750e-3,
    'fb_default':750e-3,
    'fullscale':1.2,
    'DAC':rpc.TPX4_DAC_VCASCPREAMP,
    'DAC_OUT_TOP': rpc.TPX4_OUT_VCASCPREAMP_TOP,
    'DAC_OUT_BOT': rpc.TPX4_OUT_VCASCPREAMP_BOT,
  },
  'VBiasLevelShift':{
    'bits':8,
    'unit':'A',
    'xavi_default':500e-9,
    'fast_default':500e-9,
    'lp_default':100e-9,
    'fb_default':100e-9,
    'fullscale':1.45e-6,
    'DAC':rpc.TPX4_DAC_VBIASLEVELSHIFT,
    'DAC_OUT_TOP': rpc.TPX4_OUT_VBIASLEVELSHIFTPMOS_TOP,
    'DAC_OUT_BOT': rpc.TPX4_OUT_VBIASLEVELSHIFTPMOS_BOT,
  },
  'VBiasIkrum':{
    'bits':8,
    'unit':'A',
    'xavi_default':1.6e-9,
    'fast_default':1e-9,
    'lp_default':1e-9,
    'fb_default':1.6e-9,
    'fullscale':100e-9,
    'DAC':rpc.TPX4_DAC_VBIASIKRUM,
    'DAC_OUT_TOP':rpc.TPX4_OUT_VBIASIKRUM_TOP,
    'DAC_OUT_BOT':rpc.TPX4_OUT_VBIASIKRUM_BOT,
  },
  'VFBK':{
    'bits':8,
    'unit':'V',
    'xavi_default':500e-3,
    'fast_default':500e-3,
    'lp_default':500e-3,
    'fb_default':500e-3,
    'fullscale':1.2,
    'DAC':rpc.TPX4_DAC_VFBK,
    'DAC_OUT_TOP':rpc.TPX4_OUT_VBFK_TOP,
    'DAC_OUT_BOT':rpc.TPX4_OUT_VBFK_BOT,
  },
  'VTpulseCoarse':{
    'bits':8,
    'unit':'V',
    'xavi_default':600e-3,
    'fast_default':600e-3,
    'lp_default':600e-3,
    'fb_default':600e-3,
    'fullscale':1.2,
    'DAC':rpc.TPX4_DAC_VTPULSECOARSE,
    'DAC_OUT_TOP': rpc.TPX4_OUT_VTPULSECOARSE_TOP,
    'DAC_OUT_BOT': rpc.TPX4_OUT_VTPULSECOARSE_BOT,
  },
  'VTpulseFine':{
    'bits':14,
    'unit':'V',
    'xavi_default':600e-3,
    'fast_default':600e-3,
    'lp_default':600e-3,
    'fb_default':600e-3,
    'fullscale':1.2,
    'DAC':rpc.TPX4_DAC_VTPULSEFINE,
    'DAC_OUT_TOP': rpc.TPX4_OUT_VTPULSEFINE_TOP,
    'DAC_OUT_BOT': rpc.TPX4_OUT_VTPULSEFINE_BOT,
  },
  'VBiasDiscTailNMOS':{
    'bits':8,
    'unit':'A',
    'xavi_default':865e-9,
    'fast_default':1.34e-6,
    'lp_default':210e-9,
    'fb_default':210e-9,
    'fullscale':3.1e-6,
    'DAC':rpc.TPX4_DAC_VBIASDISCTAILNMOS,
    'DAC_OUT_TOP': rpc.TPX4_OUT_VBIASDISCTAILNMOS_TOP,
    'DAC_OUT_BOT': rpc.TPX4_OUT_VBIASDISCTAILNMOS_BOT,
  },
  'VBiasDiscPMOS':{
    'bits':8,
    'unit':'A',
    'xavi_default':400e-9,
    'fast_default':920e-9,
    'lp_default':300e-9,
    'fb_default':300e-9,
    'fullscale':3.6e-6,
    'DAC':rpc.TPX4_DAC_VBIASDISCPMOS,
    'DAC_OUT_TOP': rpc.TPX4_OUT_VBIASDISCPMOS_TOP,
    'DAC_OUT_BOT': rpc.TPX4_OUT_VBIASDISCPMOS_BOT,
  },
  'VBiasDiscTRAFF':{
    'bits':8,
    'unit':'A',
    'xavi_default':780e-9,
    'fast_default':500e-9,
    'lp_default':250e-9,
    'fb_default':250e-9,
    'fullscale':4e-6,
    'DAC':rpc.TPX4_DAC_VBIASDISCTRAFF,
    'DAC_OUT_TOP': rpc.TPX4_OUT_VBIASDISCTRAFF_TOP,
    'DAC_OUT_BOT': rpc.TPX4_OUT_VBIASDISCTRAFF_BOT,
  },
  'VCascDisc':{
    'bits':8,
    'unit':'V',
    'xavi_default':550e-3,
    'fast_default':550e-3,
    'lp_default':550e-3,
    'fb_default':550e-3,
    'fullscale':1.2,
    'DAC':rpc.TPX4_DAC_VCASCDISC,
    'DAC_OUT_TOP': rpc.TPX4_OUT_VCASCDISC_TOP,
    'DAC_OUT_BOT': rpc.TPX4_OUT_VCASCDISC_BOT,
  },
  'VThreshold':{
    'bits':14,
    'unit':'V',
    'xavi_default':540e-3,
    'fast_default':540e-3,
    'lp_default':540e-3,
    'fb_default':540e-3,
    'fullscale':1.2,
    'DAC':rpc.TPX4_DAC_VTHRESHOLD,
    'DAC_OUT_TOP': rpc.TPX4_OUT_VTHRESHOLD_TOP,
    'DAC_OUT_BOT': rpc.TPX4_OUT_VTHRESHOLD_BOT,
  },
  'VBiasDAC':{
    'bits':8,
    'unit':'A',
    'xavi_default':40e-9,  ### Xavi / Reference
    'fast_default':78e-9,
    'lp_default':16e-9,
    'fb_default':16e-9,
    'fullscale':160e-9,
    'DAC':rpc.TPX4_DAC_VBIASDAC,
    'DAC_OUT_TOP': rpc.TPX4_OUT_VBIASDAC_BIAS_TOP,
    'DAC_OUT_BOT': rpc.TPX4_OUT_VBIASDAC_BIAS_BOT,
  },
}

class DACs:
  def __init__(self,tpx4_stub,chip_index, adc_half='TOP',adc='internal',initialize=True, debug=True, dac_mode = 'fb_default'):

    self.tpx4 = tpx4_stub
    self.debug = debug
    self.chip_index = chip_index
    self.dac_mode = dac_mode
    self.dacs = dacs_lib

    print(f'Setting dacs to dac mode {dac_mode}')
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
      # We're going to use the internal ADC, configure at 4 MHz with 32768 ADC cycles
      self.tpx4.ConfigAdc(rpc.Tpx4AdcConfig(clock_ref=4000000, nperiods=32*1024))

    readout_config = self.tpx4.ReadoutGetConfig(rpc.ChipIndex(idx=self.chip_index))
    self.hole_polarity = readout_config.polarity
    self.low_gain = readout_config.gain
    #print(f'Polarity: {readout_config.polarity}')
    #print(f'Gain: {readout_config.gain}')

    for dac,data in self.dacs.items():
      #Set DAC default value
      if dac_mode in data.keys():
        if initialize == True:
          if debug: print(f'Set DAC {dac} to default value {data[dac_mode]:.3G} {data['unit']} ')
          self.setDAC(dac,value=data[dac_mode],debug=self.debug)
        else:
          #Initialize dac_code as None
          self.dacs[dac]['dac_code'] = None
        #Read DAC on debug mode (populate readback value in dictionary)
        self.readDAC(dac,debug=self.debug)
      else:
        print(f'ERROR: dac_mode {dac_mode} not found!')
        sys.exit(1)

  def linearize_voltage_dac(self,dac_name,target_value,initial_dac_code):
    #Start to linearize from the initial value
    dac_code = initial_dac_code
    loop_counter = 0

    #Iterate within a maximum number given by LOOP_MAX_ITERATIONS
    while loop_counter < LOOP_MAX_ITERATIONS:
      #Read the current DAC value
      feedback = self.readDAC(dac_name,debug=False)

      #Compute the error from the target, decide if we need to move up or down
      error = target_value - feedback
      delta_dac_code = round(error/self.dacs[dac_name]['resolution'])

      #When approaching the final value, slow down the delta dac to +1 or -1 depending on delta polarity
      if abs(delta_dac_code) < 5:
        delta_dac_code = (delta_dac_code > 0) - (delta_dac_code < 0)

      #print(f'Iteration {loop_counter}. Error {error:.3f}. Target {target_value:.3f}. Rbv {feedback:.3f}. Delta dac code {delta_dac_code}')

      #Calculate the next dac_code step
      dac_code = dac_code + delta_dac_code

      #If calculated delta is 0 break the loop
      if delta_dac_code == 0:
        break
      #else set the new DAC value
      else:
        #Set the DAC
        self.setDAC_lowlevel(dac_name,dac_code,debug=False)

      loop_counter +=1

    #Return the loop counter, the last feedback value and the final dac_code
    return loop_counter,feedback,dac_code

  def setDAC(self,dac_name,value,debug=True):
    if dac_name in self.dacs.keys():
      if self.dacs[dac_name]['bits'] == 8:
        self.dacs[dac_name]['resolution'] = self.dacs[dac_name]['fullscale']/(2**(self.dacs[dac_name]['bits']))
        dac_code = round(value/self.dacs[dac_name]['resolution'])&0xFF
        # Write DAC value
        self.setDAC_lowlevel(dac_name,dac_code,debug=False)
        feedback = self.readDAC(dac_name,debug=False)
        if debug: print(f'Write DAC {dac_name}: {value:.3g} V. Initial DAC code: 0x{dac_code:02X}')

        #Iterate to find best value for voltage DACs
        if self.dacs[dac_name]['unit'] == 'V':
          loop_counter,feedback,dac_code = self.linearize_voltage_dac(dac_name,value,dac_code)

          if debug: print(f'Optimized DAC {dac_name} to: {value:.5f} V with {loop_counter} iterations. DAC code: 0x{dac_code:04X} and readback value: {feedback:.5f} ')

      elif self.dacs[dac_name]['bits'] == 14:

        #fullrange is around 500mV per coarse adjustment
        #resolution is 10 bits
        #we can choose three coarse regions to work, based on DAC VTHRESHOLD scan analysis, as the first iteration point
        LIN_RANGE_1 = 400e-3
        LIN_RANGE_2 = 800e-3
        if value <= LIN_RANGE_1:
          #Specific for second coarse range
          coarse = 2 #from 0 to LIN_RANGE_1
          V_START = 0
          V_END = 0.63
        elif value <= LIN_RANGE_2:
          coarse = 5 #from LIN_RANGE_1 to LIN_RANGE_2
          V_START = 0.34
          V_END = 0.89
        else:
          coarse = 8 #from LIN_RANGE_2 to saturation (1.150V)
          V_START = 0.59
          V_END = 1.15
        self.dacs[dac_name]['resolution'] = (V_END - V_START)/(2**10)
        fine_adj = round((value-V_START)/self.dacs[dac_name]['resolution'])
        dac_code = coarse << 10 | fine_adj

        # Write DAC value
        self.setDAC_lowlevel(dac_name,dac_code,debug=False)
        feedback = self.readDAC(dac_name,debug=False)
        if debug: print(f'Write DAC {dac_name}: {value:.3g} V. Initial DAC code: 0x{dac_code:04X}')

        #Iterate to find best value for voltage DACs
        if self.dacs[dac_name]['unit'] == 'V':
          loop_counter,feedback,dac_code = self.linearize_voltage_dac(dac_name,value,dac_code)
          if debug: print(f'Optimized DAC {dac_name} to: {value:.5f} V with {loop_counter} iterations. DAC code: 0x{dac_code:04X} and readback value: {feedback:.5f} ')

      else:
        print(f'ERROR: dac {dac_name} with {self.dacs[dac_name]['bits']} bits need to be implemented')
        raise SystemExit

      #Save variables to use in the future
      self.dacs[dac_name]['readback'] = feedback
      self.dacs[dac_name]['dac_code'] = dac_code

      #Return last feeedback value
      return feedback
    else:
      print(f'ERROR: dac {dac_name} not in dac list. Cannot write')
      raise SystemExit

  def readDAC(self,dac_name,debug=True):
    if dac_name in self.dacs.keys():
      #Read DAC value
      value = self.tpx4.AdcRead(rpc.Tpx4AdcRequest(idx=self.chip_index, dac_out=self.dacs[dac_name][f'DAC_OUT_{self.adc_half}'], external=self.adc_external)).value
      #Save variables to use in the future
      self.dacs[dac_name]['readback'] = value
      if debug: print(f'Read DAC {dac_name}: {value:.5f} V')
      return value
    else:
      print(f'ERROR: dac {dac_name} not in dac list. Cannot read')
      raise SystemExit

  def setDAC_lowlevel(self,dac_name,dac_code,debug=True):
    if dac_name in self.dacs.keys():
      #Read DAC value
      self.tpx4.SetDacs(rpc.DacValueList(idx=self.chip_index,items=[rpc.DacValue(dac=self.dacs[dac_name]['DAC'], value=dac_code)]))
      #Save dac_code to use in the future
      self.dacs[dac_name]['dac_code'] = dac_code
      if debug: print(f'Write DAC {dac_name} with dac_code: {dac_code:04X}')
    else:
      print(f'ERROR: dac {dac_name} not in dac list. Cannot write')
      raise SystemExit

  def conf_threshold(self,
                  THR_e=1000,
                  FBK_V=None,
                  force_FBK=True,
                  debug=True):

    # Nominal calculation of gain does not represent the real gain, Timepix4 CSA parasitic capacitance is around 1.7fF
    #Cf_low = 6e-15
    #Cf_high = 3e-15
    #Cf = Cf_low if LOW_GAIN else Cf_high
    # capacitance = (n*q)/V --> gain (V/e) = q/capacitance
    #Gain_Ve = 1.6e-19/Cf
    #We will use the value from Xavi scripts in V/e

    if FBK_V == None:
      FBK_V = self.dacs['VFBK'][self.dac_mode]

    Gain_Ve = 20.5e-6 if self.low_gain else 34.5e-6

    THR_FBK_V=THR_e*Gain_Ve

    #Force FBK or only readback the value
    if force_FBK:
      rb_fbk = self.setDAC('VFBK',value=FBK_V,debug=debug)
    else:
      rb_fbk = self.readDAC('VFBK',debug=debug)

    THR_V = (rb_fbk - THR_FBK_V) if self.hole_polarity else (rb_fbk + THR_FBK_V)

    rb_th = self.setDAC('VThreshold',value=THR_V,debug=debug)

    meas_threshold_v = (rb_fbk - rb_th) if self.hole_polarity else (rb_th - rb_fbk)
    meas_threshold_e = meas_threshold_v/Gain_Ve

    if debug:
        print(f'Operation threshold target: {THR_e} e. Threshold measured {meas_threshold_e} e')
        print(f'DAC VFBK target {FBK_V:.3f}. Measured {rb_fbk:.3f}')
        print(f'DAC VThreshold target {THR_V:.3f}. Measured {rb_th:.3f}')

    return meas_threshold_e