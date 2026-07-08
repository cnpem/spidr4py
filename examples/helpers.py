import time
import sys
import argparse
import numpy as np
import grpc
from typing import List, Tuple, Dict

from spidr4 import rpc, tpx4tools, find
import example_config as ec

# Contains the argument parser namespace
_cl_ns = None


def cl_parse(with_chip_idx: bool = True, args: Dict[str, dict] = dict({})):
    global _cl_ns
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, help="SPIDR4 host name, or index", default=ec.DEFAULT_HOST)
    parser.add_argument("--port", type=int, help="SPIDR4 RPC port", default=ec.DEFAULT_PORT)
    if with_chip_idx:
        parser.add_argument("--chip-idx", type=int, default=ec.DEFAULT_CHIP_INDEX)

    for arg, opts in args.items():
        parser.add_argument(arg, **opts)

    _cl_ns = parser.parse_args(sys.argv[1:])
    
    return _cl_ns


class ConnectionWrapper(object):
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection.__enter__()

    def __exit__(self, exc_type, exc_value, exc_tb):
        if exc_value and hasattr(exc_value, 'code') and callable(exc_value.code):
            # Quack!
            code = exc_value.code()
            if code == grpc.StatusCode.UNIMPLEMENTED:
                print("======================================================================================\n"
                      " The error you are receiving is likely due to an older version of the SPIDR4 firmware\n"
                      " Please consider updating your firmware to a more recent version - SPIDR4 TEAM\n"
                      "======================================================================================")

        return self.connection.__exit__(exc_type, exc_value, exc_tb)


def cl_connect():
    return ConnectionWrapper(find.find_and_connect(_cl_ns.host, port=_cl_ns.port))


def cl_chip_idx():
    return _cl_ns.chip_idx


def config_test_pulse(tpx4, chip_idx):
    # Configure event-based readout
    # ------------------------------------------------------------------------------------------------------
    readoutCfg = rpc.Tpx4ReadoutConfig(
        idx=chip_idx,
        mode=rpc.TPX4_READOUT_TOA_TOT,
        pc24b_thr=1
    )
    tpx4.ReadoutSetConfig(readoutCfg)

    # Configure Pixel Matrix
    # ------------------------------------------------------------------------------------------------------
    pixel_cfg = tpx4tools.PixelConfig(dac=31, power_enable=True, tp_enable=False, mask=True).word
    pixel_cfg_tp = tpx4tools.PixelConfig(dac=31, power_enable=True, tp_enable=True, mask=False).word
    spixel_cfg = np.full((512, 448), pixel_cfg, dtype=np.uint8)

    img = get_test_image()
    for y in range(0, 512):
        for x in range(0, 448):
            if img[y,x]:
                spixel_cfg[y, x] = pixel_cfg_tp

    config_blob = tpx4tools.logic2chip_cfg_matrix(spixel_cfg)

    tpx4.ConfigPixels(
        rpc.Tpx4PixelConfig(
            idx=chip_idx,
            config=config_blob.tobytes()
        )
    )

    # Configure shutter
    # ------------------------------------------------------------------------------------------------------
    tpx4.ShutterSetConfig(
        rpc.Tpx4ShutterConfig(
            idx=chip_idx,
            mode=rpc.TPX4_SHUTTER_MODE_PROG_SINGLE,
            input=rpc.TPX4_SHUTTER_INPUT_SLOW_CONTROL,
            prog_open_us=10,
            prog_close_us=10
        )
    )

    # Enable the test-pulse
    # ------------------------------------------------------------------------------------------------------
    tpx4.TestPulseEnable(rpc.ChipIndex(idx=chip_idx))


def scan_tp(tpx4, chip_idx):
    # tpx4.ShutterOpen(rpc.ChipIndex(idx=chip_idx))
    sys.stdout.write("Pulsing columns")
    for i in range(224):
        if i % 8 == 0:
            sys.stdout.write(".")
            sys.stdout.flush()
        try:
            # Configure the test pulse
            # ------------------------------------------------------------------------------------------------------
            tpConfig = rpc.Tpx4TestPulseConfig(
                idx=chip_idx,
                count=1,
                period_on_us=1,
                period_off_us=1,
                digital=True,
                link_shutter=True,
                shutter2tp_latency=2,
                columns=[
                        rpc.Tpx4ColumnAddress(half=rpc.Tpx4Half.TPX4_TOP, column=i),
                        rpc.Tpx4ColumnAddress(half=rpc.Tpx4Half.TPX4_BOTTOM, column=i)
                    ]
            )
            tpx4.TestPulseSetConfig(tpConfig)
        except:
            raise RuntimeError("Failed to set enable TP columns. You may be using an old version of the firmware")

        # Test-pulse start
        # ------------------------------------------------------------------------------------------------------
        tpx4.TestPulseStart(rpc.ChipIndex(idx=chip_idx))

        # Wait for some data...
        time.sleep(0.01)
    print("Done!", file=sys.stdout)

    tpx4.ShutterClose(rpc.ChipIndex(idx=chip_idx))

def get_test_image():
    from io import BytesIO
    import base64

    img_data = """
    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
    AQABADUAAAB9HgAAAAA=
    """
    return np.load(BytesIO(base64.b64decode(img_data)))['img']


def save_or_show(plt):
    import matplotlib as mpl

    if mpl.get_backend() == 'agg':
        import tempfile
        temp_file = tempfile.mktemp(suffix=".png", prefix="testpulse")
        plt.savefig(temp_file)
        print(f"Can't plot, save to {temp_file}")
        plt.clf()
    else:
        plt.show()



if __name__ == "__main__":
    print("helpers is not an example, just a collection of tools used by the examples")
