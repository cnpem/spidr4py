import grpc
from spidr4 import rpc, tpx4tools
import numpy as np
try:
    import matplotlib.pyplot as plt
except ImportError:
    import sys
    print("matplotlib is required for this example", file=sys.stderr)
    sys.exit(1)

import helpers

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=True)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get timepix 4 service
        tpx4 = rpc.Timepix4Stub(channel)

        # Set pixel config with random DAC on all pixels
        pixelConfig = np.random.randint(0, 31, size=(512, 448), dtype=np.uint8)
        pixelConfig |= 0x20

        # Convert the logical pixel to timepix4 matrix indices
        pixelConfigBlob = tpx4tools.logic2chip_cfg_matrix(pixelConfig)

        # Upload pixel config to timepix 4
        tpx4.ConfigPixels(
            rpc.Tpx4PixelConfig(
                idx=helpers.cl_chip_idx(),
                config=pixelConfigBlob.tobytes()
            )
        )

        # Read it back
        pixelConfigBlob2 = tpx4.ConfigGetPixels(
            rpc.ChipIndex(idx=helpers.cl_chip_idx())
        ).config

        # Convert it to x,y
        readBackConfig = tpx4tools.chip2logic_cfg_matrix(
            np.frombuffer(pixelConfigBlob2, dtype=np.uint8)
        )

        # Check errors
        print("Checking for errors...")
        readBackConfig[300, 200] = 0
        y_errs, x_errs = np.where(pixelConfig != readBackConfig)
        for y_err, x_err in zip(y_errs, x_errs):
            print(f"Error row {y_err} and col {x_err}: "
                  f"written={pixelConfig[y_err,x_err]}, readback={readBackConfig[y_err,x_err]}")
        print(f"... {len(y_errs)} error(s) found")

        readBackConfig &= 0x3f

        # plot the two matrices
        fig, axs = plt.subplots(1, 2, sharey=True)

        axs[0].imshow(pixelConfig, vmin=0, vmax=63)
        axs[1].imshow(readBackConfig, vmin=0, vmax=63)
        axs[0].set_title("Written")
        axs[1].set_title("Read-back")
        axs[0].set_ylabel("Rows")
        axs[0].set_xlabel("Colums")
        axs[1].set_xlabel("Colums")
        plt.tight_layout()
        plt.show()
