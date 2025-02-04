#!/bin/env python3
#
# This example shows different ways to control the shutter. Note that it is not
# exhaustive.
#
import threading

import time

import numpy as np
from spidr4 import rpc, tpx4tools, utils, stream, tpx4regs
import queue
import matplotlib.pyplot as plt
import helpers

DEMOS = (1, 2, 3, 4, 5,)

if __name__ == "__main__":
    ns = helpers.cl_parse(with_chip_idx=True)

    print("===============================================================")
    print("Shutter demo - Shows various ways to control the shutter")
    print("Note that demo 4 and 5 require an external shutter  source to")
    print("be connected via the HDMI connector on the back of the SPIDR4")
    print("system")
    print("===============================================================")
    input("Press enter to continue")

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the services
        # ------------------------------------------------------------------------------------------------------
        ctrl = rpc.ControlInfoStub(channel)
        tpx4 = rpc.Timepix4Stub(channel)
        trigger = rpc.TriggerStub(channel)
        datastream = rpc.DataStreamStub(channel)

        # Reset the pixel chips (will also load the default configuration)
        # ------------------------------------------------------------------------------------------------------
        ctrl.ResetPixelChips(rpc.EMPTY)

        # Configure for test-pulse
        # ------------------------------------------------------------------------------------------------------
        # Configure the test pulse
        # ------------------------------------------------------------------------------------------------------
        tpConfig = rpc.Tpx4TestPulseConfig(
                idx=helpers.cl_chip_idx(),
                count=3,
                period_on_us=100,
                period_off_us=900,
                digital=True,
                link_shutter=False,
                columns = [
                        rpc.Tpx4ColumnAddress(half=rpc.TPX4_TOP, column=223),
                        rpc.Tpx4ColumnAddress(half=rpc.TPX4_BOTTOM, column=0),
                ]
        )
        tpx4.TestPulseSetConfig(tpConfig)

        # Configure event-based readout
        # ------------------------------------------------------------------------------------------------------
        readoutCfg = rpc.Tpx4ReadoutConfig(
                idx=helpers.cl_chip_idx(),
                mode=rpc.TPX4_READOUT_TOA_TOT,
                pc24b_thr=1
        )
        tpx4.ReadoutSetConfig(readoutCfg)

        # Configure Pixel Matrix
        # ------------------------------------------------------------------------------------------------------
        pixel_cfg = tpx4tools.PixelConfig(dac=31, power_enable=True, tp_enable=False, mask=False).word
        pixel_cfg_tp = tpx4tools.PixelConfig(dac=31, power_enable=True, tp_enable=True, mask=False).word
        spixel_cfg = np.full((512, 448), pixel_cfg, dtype=np.uint8)

        # Enable bottom TP and top TP
        spixel_cfg[0][0] = pixel_cfg_tp
        spixel_cfg[511][447] = pixel_cfg_tp
    
        config_blob = tpx4tools.logic2chip_cfg_matrix(spixel_cfg)

        tpx4.ConfigPixels(
                rpc.Tpx4PixelConfig(
                        idx=helpers.cl_chip_idx(),
                        config=config_blob.tobytes()
                )
        )

        tpx4.StatusMonSetConfig(rpc.Tpx4StatusMonConfig(
            idx=helpers.cl_chip_idx(),
            enable=True
        ))
            
        tpx4.TestPulseEnable(rpc.ChipIndex(idx=helpers.cl_chip_idx()))

        q = queue.Queue()
        
        daq_stop = False
        def read_thread(q):
            global daq_stop
            prt = stream.packet_read_thread(tpx4, q, helpers.cl_chip_idx(), forward_empty=False)
            # Read-data and put in matrix
            # ------------------------------------------------------------------------------------------------------
            while not daq_stop:
                for data in stream.queue_generator(q, 5):
                    pkt = tpx4tools.decode_dd_packet(data)
                    if isinstance(pkt, tpx4tools.ToAToTPacket):
                                x, y = tpx4tools.chip_coords2logic(pkt.Top, pkt.EoC, pkt.SPGroup, pkt.SPixel, pkt.Pixel)
                                print(f"Test pulse ({x},{y})")
                    elif isinstance(pkt, tpx4tools.ControlStatusPacket):
                        print(f"top={pkt.top}, header={tpx4tools.cs_lookup(pkt.header)}, segment={pkt.segment}, data={pkt.data}")
                    else:
                        print(f"Unexpected packet: {pkt}")
            
            print("Wait complete, stopping threads")
            prt.stop()
        

        show_thread = threading.Thread(target=read_thread, args=(q,), daemon=True)
        show_thread.start()
        time.sleep(0.1)


        if 1 in DEMOS:
            print("===============================================================")
            print("DEMO 1: Manual open/close on chip")
            print("===============================================================")
            tpx4.ShutterSetConfig(
                rpc.Tpx4ShutterConfig(
                        idx=helpers.cl_chip_idx(),
                        mode=rpc.TPX4_SHUTTER_MODE_MANUAL,
                        input=rpc.TPX4_SHUTTER_INPUT_SLOW_CONTROL
                )
            )
            
            tpx4.ShutterOpen(rpc.EMPTY)
            
            tpx4.TestPulseStart(rpc.ChipIndex(idx=helpers.cl_chip_idx()))
            
            time.sleep(2)
    
            tpx4.ShutterClose(rpc.EMPTY)
                
            time.sleep(1)
    
        if 2 in DEMOS:
            print("===============================================================")
            print("DEMO 2: Manual open/close SPIDR4 trigger")
            print("===============================================================")
            tpx4.ShutterSetConfig(
                rpc.Tpx4ShutterConfig(
                        idx=helpers.cl_chip_idx(),
                        mode=rpc.TPX4_SHUTTER_MODE_MANUAL,
                        input=rpc.TPX4_SHUTTER_INPUT_PAD
                )
            )
                
            trigger.SetConfig(
                rpc.TriggerConfig(
                    shutter_input = rpc.SHUTTER_IN_SOFTWARE
                )
            )
            
            # Reset test pulse
            tpx4.TestPulseSetConfig(tpConfig)
        
            trigger.Enable(rpc.EMPTY)
            trigger.ShutterOpen(rpc.EMPTY)
            
            tpx4.TestPulseStart(rpc.ChipIndex(idx=helpers.cl_chip_idx()))
    
            time.sleep(2)
            
            trigger.ShutterClose(rpc.EMPTY)
                
            time.sleep(1)
            trigger.Disable(rpc.EMPTY)
    
        if 3 in DEMOS:
            print("===============================================================")
            print("DEMO 3: Using SPIDR4 auto open/close")
            print("===============================================================")
            tpx4.ShutterSetConfig(
                rpc.Tpx4ShutterConfig(
                    idx=helpers.cl_chip_idx(),
                    mode=rpc.TPX4_SHUTTER_MODE_MANUAL,
                    input=rpc.TPX4_SHUTTER_INPUT_PAD
                )
            )
 
            trigger.SetConfig(
                rpc.TriggerConfig(
                    shutter_input = rpc.SHUTTER_IN_AUTO_GEN,
                    auto_shutter_open_us = 3000000,
                    auto_shutter_close_us = 1,
                    shutter_count = 1
                )
            )
            
            # Reset test pulse
            tpx4.TestPulseSetConfig(tpConfig)
            
            trigger.Enable(rpc.EMPTY)
            trigger.StartAutoShutter(rpc.EMPTY)
            
            tpx4.TestPulseStart(rpc.ChipIndex(idx=helpers.cl_chip_idx()))
            
            time.sleep(3)
            
            trigger.Disable(rpc.EMPTY)
    
        if 4 in DEMOS:
            print("===============================================================")
            print("DEMO 4: Using SPIDR4 external shutter")
            print("===============================================================")
            print("For this DEMO, please enable an external shutter signal on the")
            print("HDMI connector. The signal should have period of 1 second and a")
            print("duty cycle of 1% (10 ms).")
            print("You should see about 10 test-pulse (5 top, 5 bottom) packets per shutter period")
            input("Press enter to continue...")

            # configure TPX4 to accept external shutter
            tpx4.ShutterSetConfig(
                rpc.Tpx4ShutterConfig(
                    idx=helpers.cl_chip_idx(),
                    mode=rpc.TPX4_SHUTTER_MODE_MANUAL,
                    input=rpc.TPX4_SHUTTER_INPUT_PAD
                )
            )
            
            # Configure SPIDR4 trigger to pass through external shutter 
            trigger.SetConfig(
                rpc.TriggerConfig(
                    shutter_input = rpc.SHUTTER_IN_EXTERNAL,
                    busy_output = rpc.BUSY_OUT_SHUTTER
                )
            )
    
            # Reset test pulse to give long test pulses for demo.
            tpConfig = rpc.Tpx4TestPulseConfig(
                idx=helpers.cl_chip_idx(),
                count=3000,
                period_on_us=400,
                period_off_us=1600,
                digital=True,
                link_shutter=False,
                columns = [
                    rpc.Tpx4ColumnAddress(half=rpc.TPX4_TOP, column=223),
                    rpc.Tpx4ColumnAddress(half=rpc.TPX4_BOTTOM, column=0),
                ]
            )
            tpx4.TestPulseSetConfig(tpConfig)
            
            trigger.Enable(rpc.EMPTY)
            
            trigger.ResetShutterCounter(rpc.EMPTY)
            
            tpx4.TestPulseStart(rpc.ChipIndex(idx=helpers.cl_chip_idx()))
    
            # input("Press enter to continue...")
            
            
            time.sleep(3)
    
            trigger.Disable(rpc.EMPTY)
            
            status = trigger.GetStatus(rpc.EMPTY)
            print(f"Received shutters: {status.shutter_counter}")
       
        if 5 in DEMOS:
            print("===============================================================")
            print("DEMO 5: Using SPIDR4 external shutter + AUTO TRIGGER")
            print("===============================================================")
            print("For this DEMO, please enable an external shutter signal on the")
            print("HDMI connector. The signal should have period of 1 second and a")
            print("duty cycle of 1% (10 ms).")
            print("This demo will limit the open time to 4 ms, generating ~4 test pulse packets per shutter")
            input("Press enter to continue...")

            # configure TPX4 to accept external shutter
            tpx4.ShutterSetConfig(
                rpc.Tpx4ShutterConfig(
                    idx=helpers.cl_chip_idx(),
                    mode=rpc.TPX4_SHUTTER_MODE_MANUAL,
                    input=rpc.TPX4_SHUTTER_INPUT_PAD
                )
            )

            # Configure SPIDR4 trigger to pass through external shutter 
            trigger.SetConfig(
                rpc.TriggerConfig(
                    shutter_input=rpc.SHUTTER_IN_AUTO_GEN_EXT_START,
                    busy_output=rpc.BUSY_OUT_SHUTTER,
                    auto_shutter_open_us=4000,
                    auto_shutter_close_us=1,
                    shutter_count=1                       
                )
            )

            # Reset test pulse to give long test pulses for demo.
            tpConfig = rpc.Tpx4TestPulseConfig(
                idx=helpers.cl_chip_idx(),
                count=3000,
                period_on_us=400,
                period_off_us=1600,
                digital=True,
                link_shutter=False,
                columns = [
                    rpc.Tpx4ColumnAddress(half=rpc.TPX4_TOP, column=223),
                    rpc.Tpx4ColumnAddress(half=rpc.TPX4_BOTTOM, column=0),
                ]
            )
            tpx4.TestPulseSetConfig(tpConfig)

            trigger.Enable(rpc.EMPTY)

            trigger.ResetShutterCounter(rpc.EMPTY)

            tpx4.TestPulseStart(rpc.ChipIndex(idx=helpers.cl_chip_idx()))

            time.sleep(3)

            trigger.Disable(rpc.EMPTY)

            status = trigger.GetStatus(rpc.EMPTY)
            print(f"Received shutters: {status.shutter_counter}")



        # Wait for the capture thread to stop
        # ------------------------------------------------------------------------------------------------------
        print("Shutter demo complete. Waiting for capture thread to stop")
        daq_stop = True
        show_thread.join(12)
    
        # Disable data acquisition.
        # ------------------------------------------------------------------------------------------------------
        datastream.ConfigNone(rpc.ChipIndex(idx=helpers.cl_chip_idx()))

