import grpc
from spidr4 import rpc, find
import time

if __name__ == '__main__':
    found_spidrs = find.find_spidrs4s()

    for spidr in found_spidrs:
        addresses = " , ".join(spidr.addresses)
        print(f"Found {spidr.hostname}, possible addresses={addresses}:")
        try:
            with spidr.connect() as ch:
                print(f" ? Connected using : {ch.host}")
                control = rpc.ControlInfoStub(ch)
                fwversion = control.GetFirmwareVersion(rpc.EMPTY)
                serial = control.GetSerial(rpc.EMPTY).value
                noofchips = len(control.GetPixelChipInfo(rpc.EMPTY).items)
                print(f" * No of pxielchips: {noofchips}")
                print(f" * Firmware version: {fwversion.commit_info}")
                print(f" * Serial          : {serial:016x}")
        except:
            print("  [connection failed!]")