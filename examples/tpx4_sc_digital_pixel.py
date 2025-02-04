#!/bin/env python3
#
# This example shows the usage of the digital pixel
#
import threading

import time

import numpy as np
from spidr4 import rpc, tpx4tools, stream
import queue
import helpers

if __name__ == "__main__":
    ns = helpers.cl_parse(with_chip_idx=True)

    print("===============================================================")
    print("Digital Pixel demo")
    print("Pleae connect digital pixel 1 with a 100 us period and 10% (10 us)")
    print("duty-cycle. If working properly you should see about 20 pulses of")
    print("10 us. 10 Pulses per enabled pixel.")
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

        # We'll make SPIDR4 open the shutter, and close it after a defined time (1 ms)
        # ------------------------------------------------------------------------------------------------------
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
                auto_shutter_open_us = 1000,        # open for 1 ms
                auto_shutter_close_us = 1,
                shutter_count = 1
            )
        )

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
        pixel_cfg = tpx4tools.PixelConfig(dac=31, power_enable=False, tp_enable=False, mask=True).word
        pixel_cfg_dp = tpx4tools.PixelConfig(dac=31, power_enable=True, tp_enable=False, mask=False).word
        pixel_cfg_mtx = np.full((512, 448), pixel_cfg, dtype=np.uint8)

        # Enable top column 0, pixel 0, and top column 222, pixel 0. 
        pixel_cfg_mtx[511][0] = pixel_cfg_dp
        pixel_cfg_mtx[511][444] = pixel_cfg_dp
    
        config_blob = tpx4tools.logic2chip_cfg_matrix(pixel_cfg_mtx)

        tpx4.ConfigPixels(
                rpc.Tpx4PixelConfig(
                        idx=helpers.cl_chip_idx(),
                        config=config_blob.tobytes()
                )
        )
        
        sp_cfg_arr = np.full((2,224,16), fill_value=0, dtype=int)
        
        group_cfg = tpx4tools.SPGroupConfig(digital_pixel_enable=1).word
        sp_cfg_arr[0][0][0] = group_cfg
        sp_cfg_arr[0][222][0] = group_cfg

        tpx4.ConfigSPGroups(
            rpc.Tpx4SPGroupConfig(
                idx=0,
                config=sp_cfg_arr.flatten()
            )
        )
    
        # Enable monitoring so we can see shutter rise and fall
        tpx4.StatusMonSetConfig(rpc.Tpx4StatusMonConfig(
            idx=helpers.cl_chip_idx(),
            enable=True
        ))
        
        # Do asynchronous shutter
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
                                print(f"Digital pixel pulse @ {x},{y} with {pkt.ToT*0.025}) us duration")
                    elif isinstance(pkt, tpx4tools.ControlStatusPacket):
                        print(f"top={pkt.top}, header={tpx4tools.cs_lookup(pkt.header)}, segment={pkt.segment}, data={pkt.data}")
                    else:
                        print(f"Unexpected packet: {pkt}")
            
            print("Wait complete, stopping threads")
            prt.stop()
        

        show_thread = threading.Thread(target=read_thread, args=(q,), daemon=True)
        show_thread.start()
        time.sleep(1)
        trigger.Enable(rpc.EMPTY)
        trigger.StartAutoShutter(rpc.EMPTY)

        time.sleep(1)

        # Wait for the capture thread to stop
        # ------------------------------------------------------------------------------------------------------
        print("Digital Pixel demo complete. Waiting for capture thread to stop")
        daq_stop = True
        show_thread.join(12)
    
        # Disable data acquisition.
        # ------------------------------------------------------------------------------------------------------
        datastream.ConfigNone(rpc.ChipIndex(idx=helpers.cl_chip_idx()))

