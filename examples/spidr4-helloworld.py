import grpc
from spidr4 import rpc
import helpers

if __name__ == '__main__':
    ns = helpers.cl_parse(with_chip_idx=False)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the control service
        control = rpc.ControlInfoStub(channel)

        # Get the version
        version = control.GetVersion(rpc.EMPTY)
        print(f"Version of {version.product} is {version.majr}.{version.minr}.{version.patch}"
              f" (git-info={version.commit_info})")

        fwversion = control.GetFirmwareVersion(rpc.EMPTY)
        print(f"Version of {fwversion.product} is {fwversion.majr}.{fwversion.minr}.{fwversion.patch}"
              f" (git-info={fwversion.commit_info})")

        serial = control.GetSerial(rpc.EMPTY)
        print(f"SPIDR4 serial: {serial.value:016x}")

        carrier = control.GetChipBoardInfo(rpc.EMPTY)
        print(f"Chip carrier board type: {carrier.type}, serial: {carrier.serial}")

        chips = control.GetPixelChipInfo(rpc.EMPTY)
        print(f"   which has has {len(chips.items)} pixelchip(s) attached:")

        for chip in chips.items:
            print(f"   -> position {chip.idx}: {rpc.PixelChipType.Name(chip.type)}"
                  f" revision={chip.revision} id={chip.chip_id:08x}")
