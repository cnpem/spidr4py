#!/bin/env python3
#
# This example performs a noise scan
#
import numpy as np
from spidr4 import rpc, tpx4tools, utils, stream
import queue
import sys
import time
import matplotlib.pyplot as plt
import helpers

HOLE_COLLECTION=True
DAC = rpc.TPX4_DAC_VTHRESHOLD
DAC_OUT = rpc.TPX4_OUT_VTHRESHOLD_TOP

def adc_read(tpx4:  rpc.Timepix4Stub, dac_code: int):
    # Write DAC value
    tpx4.SetDacs(rpc.DacValueList(idx=helpers.cl_chip_idx(),
                                  items=[rpc.DacValue(dac=DAC, value=dac_code)]))
    # Read internal ADC
    return tpx4.AdcRead(rpc.Tpx4AdcRequest(idx=helpers.cl_chip_idx(), dac_out=DAC_OUT)).value


def make_logical_threshold(tpx4: rpc.Timepix4Stub):
    # Perform Threshold scan

    DAC_SIZE = 1024
    DAC_CENTERS = (np.arange(16, dtype=int) << 10) + DAC_SIZE//2

    # We're going to use the internal ADC, configure at 20 MHz with 8192 ADC cycles
    tpx4.ConfigAdc(rpc.Tpx4AdcConfig(clock_ref=625000, nperiods=16*1024))
    # Copy all DAC values, to reset later on
    dacs = tpx4.GetDacs(rpc.EMPTY)

    # Resulting found values
    mapping = []
    print("Linearizing the 16 threshold DAC sections, please wait...")

    print(" * [ 1/16] Sampling from 0 to center of section 0")
    for w in range(DAC_CENTERS[0]+1):
        v = adc_read(tpx4, w)
        mapping.append((v, w))

    for i in range(0, 15):
        print(f" * [{i+1:2}/16] Bridging section {i} and {i+1}")
        rmap = []
        for j in range(1, DAC_SIZE//2):
            w_top = DAC_CENTERS[i+1]-j
            w_bot = DAC_CENTERS[i]+j
            v_top = adc_read(tpx4, w_top)
            v_bot = adc_read(tpx4, w_bot)
            if v_top == v_bot:
                mapping.append((v_bot, w_bot))
                break
            elif v_top < v_bot:
                break
            mapping.append((v_bot, w_bot))
            rmap.append((v_top, w_top))
        rmap.reverse()
        mapping += rmap
        w = DAC_CENTERS[i+1]
        v = adc_read(tpx4, w)
        mapping.append((v, DAC_CENTERS[i+1]))

    print(" * [16/16] Sampling from center of last section to end of DAC")
    for w in range(DAC_CENTERS[-1]+1, (1<<14)):
        v = adc_read(tpx4, w)
        mapping.append((v, w))

    tpx4.SetDacs(dacs)

    # trim top DAC saturation
    for i in range(len(mapping)-2, 0, -1):
        if mapping[i][0] < mapping[-1][0]*0.999:
            mapping = mapping[0:i+1]
            break

    v, w = np.array(mapping).transpose()
    w = w.astype(int)

    return v, w


if __name__ == "__main__":
    ns = helpers.cl_parse(with_chip_idx=True)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the services
        # ------------------------------------------------------------------------------------------------------
        ctrl = rpc.ControlInfoStub(channel)
        tpx4 = rpc.Timepix4Stub(channel)
        trig = rpc.TriggerStub(channel)

        datastream = rpc.DataStreamStub(channel)

        # Reset the pixel chips (will also load the default configuration)
        # ------------------------------------------------------------------------------------------------------
        ctrl.ResetPixelChips(rpc.EMPTY)

        # Setup DAC scan
        # ------------------------------------------------------------------------------------------------------
        # Backup current DAC settings
        dacs = tpx4.GetDacs(rpc.EMPTY)

        # here we create a continues threshold
        volts, words = make_logical_threshold(tpx4)

        # DAC=30 to avoid super pixel config update bug
        dac_nom = tpx4tools.PixelConfig(dac=16, power_enable=True, tp_enable=False, mask=False).word
        mask = tpx4tools.PixelConfig(dac=0, power_enable=True, tp_enable=False, mask=True).word

        # Set pixel config with random DAC on all pixels
        # pixelConfig = np.random.randint(dac_min, dac_max+1, size=(512, 448), dtype=np.uint8)
        pixelConfig = np.full((512, 448), dac_nom, dtype=np.uint8)
        ppu = tpx4tools.PartialPixelUpdater(tpx4, pixelConfig)

        # Configure shutter
        # ------------------------------------------------------------------------------------------------------
        readoutCfg = rpc.Tpx4ReadoutConfig(
            idx=helpers.cl_chip_idx(),
            mode=rpc.TPX4_READOUT_TOA_TOT,
            pc24b_thr=1,
            analog_frontend_mode = rpc.TPX4_AFEM_LOW_GAIN_HOLE_COLLECTION if HOLE_COLLECTION else
                                   rpc.TPX4_AFEM_LOW_GAIN_ELECTRON_COLLECTION
        )
        tpx4.ReadoutSetConfig(readoutCfg)

        # Configure shutter
        # ------------------------------------------------------------------------------------------------------
        tpx4.ShutterSetConfig(
            rpc.Tpx4ShutterConfig(
                idx=helpers.cl_chip_idx(),
                mode=rpc.TPX4_SHUTTER_MODE_MANUAL,
                input=rpc.TPX4_SHUTTER_INPUT_PAD,
                prog_open_us=0,
                prog_close_us=0
            )
        )

        trig.SetConfig(
            rpc.TriggerConfig(
                shutter_input = rpc.SHUTTER_IN_AUTO_GEN,
                auto_shutter_open_us = 100,
                auto_shutter_close_us = 1,
                shutter_count = 1
            )
        )
        trig.Enable(rpc.EMPTY)


        # Start slow-control DAC thread
        q = queue.Queue()
        prt = stream.packet_read_thread(tpx4, q, helpers.cl_chip_idx(), forward_empty=False)


        scan_hits = []
        tot_hits = 0

        if HOLE_COLLECTION:
            scan_volts = volts[::2]
            scan_words = words[::2]
        else:
            scan_volts = volts[::-2]
            scan_words = words[::-2]

        # Drain any remaining packets from the SC
        try:
            while True:
                pkt = tpx4tools.decode_dd_packet(q.get(block=True, timeout=0.001))
        except queue.Empty:
            pass


        for v, w in zip(scan_volts, scan_words):
            print(f"Scanning {v:.3f} V (dac_word={w})")
            tpx4.SetDacs(
                rpc.DacValueList(idx=0, items=[
                    rpc.DacValue(dac=rpc.TPX4_DAC_VTHRESHOLD, value=w)
                ])
            )
            dac_hits = 0
            while True:
                sys.stdout.write(".")
                sys.stdout.flush()
                hits = 0
                trig.StartAutoShutter(rpc.EMPTY)
                time.sleep(0.01)
                try:
                    while True:
                        pkt = tpx4tools.decode_dd_packet(q.get(block=True, timeout=0.001))

                        if isinstance(pkt, tpx4tools.ToAToTPacket):
                            x, y = tpx4tools.chip_coords2logic(pkt.Top, pkt.EoC, pkt.SPGroup, pkt.SPixel, pkt.Pixel)
                            # Disable received pixel packet
                            if pixelConfig[y, x] != mask:
                                    pixelConfig[y, x] = mask
                                    hits += 1
                except queue.Empty:
                    pass

                if hits > 0:
                    # Convert the logical pixel to timepix4 matrix indices
                    ppu.update(pixelConfig, validate=False)

                    dac_hits += hits
                else:
                    break

            tot_hits += dac_hits
            print(f" noisy pixels: {dac_hits}, total: {tot_hits}")
            scan_hits.append(dac_hits)


        # Wait for the capture thread to stop
        # ------------------------------------------------------------------------------------------------------
        prt.stop()

        # Disable data acquisition.
        # ------------------------------------------------------------------------------------------------------
        datastream.ConfigNone(rpc.ChipIndex(idx=helpers.cl_chip_idx()))

        # Recover DACs
        tpx4.SetDacs(dacs)

        # Reset chips
        ctrl.ResetPixelChips(rpc.EMPTY)

        # plot
        plt.gcf().set_size_inches(8, 5)
        plt.plot(scan_volts, np.array(scan_hits), ".")
        plt.grid()
        plt.xlabel("Volt")
        plt.ylabel("Pixels")
        helpers.save_or_show(plt)
