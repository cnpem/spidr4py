#!/bin/env python3
#
# This example reads a test pulse from the Timepix4 over 10 Gb Ethernet and shows the result
#
import threading

import time

import numpy as np
from spidr4 import rpc, tpx4tools, utils, stream
import queue
import matplotlib.pyplot as plt
import helpers


if __name__ == "__main__":
    ns = helpers.cl_parse(with_chip_idx=True)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the services
        # ------------------------------------------------------------------------------------------------------
        ctrl = rpc.ControlInfoStub(channel)
        tpx4 = rpc.Timepix4Stub(channel)
        datastream = rpc.DataStreamStub(channel)

        # Reset the pixel chips (will also load the default configuration)
        # ------------------------------------------------------------------------------------------------------
        ctrl.ResetPixelChips(rpc.EMPTY)

        # Configure for test-pulse
        # ------------------------------------------------------------------------------------------------------
        helpers.config_test_pulse(ctrl, tpx4, datastream, helpers.cl_chip_idx())

        # Setup verification matrix
        # ------------------------------------------------------------------------------------------------------
        img2 = np.zeros(shape=(512, 448), dtype=int)

        def async_capture(img2, tpx4):
            # Configure local data acquisition
            # ------------------------------------------------------------------------------------------------------
            q = queue.Queue()

            prt = stream.packet_read_thread(tpx4, q, helpers.cl_chip_idx(), forward_empty=False)

            # Read-data and put in matrix
            # ------------------------------------------------------------------------------------------------------
            for data in stream.queue_generator(q, 5):
                pkt = tpx4tools.decode_dd_packet(data)
                if isinstance(pkt, tpx4tools.ToAToTPacket):
                    x, y = tpx4tools.chip_coords2logic(pkt.Top, pkt.EoC, pkt.SPGroup, pkt.SPixel, pkt.Pixel)
                    img2[y,x] += 1

            print("Wait complete, stopping threads")
            prt.stop()

        capture_thread = threading.Thread(target=async_capture, args=(img2,tpx4))
        capture_thread.start()
        time.sleep(1)    # Bigger chance thread has started. Don't do this at home. Not production quality!

        # Scan through all columns of the chip
        # ------------------------------------------------------------------------------------------------------
        helpers.scan_tp(tpx4, helpers.cl_chip_idx())

        # Wait for the capture thread to stop
        # ------------------------------------------------------------------------------------------------------
        print("Test pulse scan complete. Waiting for capture thread to stop")
        capture_thread.join()

        # Disable data acquisition.
        # ------------------------------------------------------------------------------------------------------
        datastream.ConfigNone(rpc.ChipIndex(idx=helpers.cl_chip_idx()))

        # Process results
        # ------------------------------------------------------------------------------------------------------
        img = helpers.get_test_image()

        error = np.zeros(shape=(512, 448), dtype=int)
        for y in range(0, 512):
            for x in range(0, 448):
              hit = 1 if img[y,x] else 0
              if hit != img2[y, x]:
                error[y, x] = 1

        fig, (ax1, ax2) = plt.subplots(ncols=2)
        ax1.set_title("Output")
        ax2.set_title("Error")
        fig.set_size_inches(18,9)
        ax1.imshow(np.clip(img2, 0, 2), origin='lower')
        ax2.imshow(np.clip(error, 0, 1), origin='lower')
        plt.tight_layout()

        helpers.save_or_show(plt)
