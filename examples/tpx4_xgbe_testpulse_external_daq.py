#!/bin/env python3
#
# This example reads a test pulse from the Timepix4 over 10 Gb Ethernet. You should use a tool like sdaq to
# read out the result
#
import time

import numpy as np
from spidr4 import rpc, tpx4tools, utils, stream
import queue
import helpers

ns = helpers.cl_parse(with_chip_idx=True, args={
    "ip": dict(help="10 GbE server IP (#.#.#.#)", type=str, metavar='10GbE-IP'),
    "mac": dict(help="10 GbE server MAC (xx:xx:xx:xx:xx:xx:)", type=str, metavar='10GbE-MAC'),
    "--xgbe-port": dict(help="10 GbE port", type=int, default=8192)
})

xgbe_port = ns.xgbe_port
# make-up an 10gbe IP for the spidr4 module, as long as it is not the same as xgbe_host_ip
xgbe_spidr_ip = utils.inc_ip(ns.ip)

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

    # Configure the output
    # ------------------------------------------------------------------------------------------------------
    datastream.ConfigXGbe(rpc.XGbeConfig(
        idx=0,
        primary=rpc.XGbeLinkConfig(
            source_ip=xgbe_spidr_ip,
            dest_ip=ns.ip,
            dest_mac=ns.mac,
            port=xgbe_port
        )
    ))

    # Configure for test-pulse
    # ------------------------------------------------------------------------------------------------------
    helpers.config_test_pulse(ctrl, tpx4, datastream, helpers.cl_chip_idx())

    # Scan through all columns of the chip
    # ------------------------------------------------------------------------------------------------------
    helpers.scan_tp(tpx4, helpers.cl_chip_idx())

    # Disable data acquisition.
    # ------------------------------------------------------------------------------------------------------
    datastream.ConfigNone(rpc.ChipIndex(idx=helpers.cl_chip_idx()))



