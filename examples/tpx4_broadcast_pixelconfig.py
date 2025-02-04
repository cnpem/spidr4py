import numpy as np
import matplotlib.pyplot as plt

from spidr4 import rpc, tpx4tools
import helpers

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=True)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:

        # Create a timepix 4 service
        tpx4 = rpc.Timepix4Stub(channel)

        NO_OF_PIXELS = 512 * 448
        BC_PIXELS = 32

        # Set pixel config for even columns
        pixelConfigEven = np.array(range(0, 32), dtype=np.uint8)
        pixelConfigEven |= 0x20

        # Set pixel config for odd columns
        pixelConfigOdd = np.array(range(31, -1, -1), dtype=np.uint8)
        pixelConfigOdd |= 0x20

        # Specify even columns
        evenColumns = [
            rpc.Tpx4ColumnAddress(
                half=rpc.TPX4_TOP if i // 112 == 0 else rpc.TPX4_BOTTOM,
                column=(i % 112) * 2
            ) for i in range(224)
        ]

        # Specify odd columns
        oddColumns = [
            rpc.Tpx4ColumnAddress(
                half=rpc.TPX4_TOP if i // 112 == 0 else rpc.TPX4_BOTTOM,
                column=(i % 112) * 2 + 1
            ) for i in range(224)
        ]

        # Set even columns
        tpx4.ConfigPixelsBroadcast(
            rpc.Tpx4BroadcastPixelConfig(
                idx=helpers.cl_chip_idx(),
                columns=evenColumns,
                config=pixelConfigEven.tobytes()
            )
        )

        # Set odd columns
        tpx4.ConfigPixelsBroadcast(
            rpc.Tpx4BroadcastPixelConfig(
                idx=helpers.cl_chip_idx(),
                columns=oddColumns,
                config=pixelConfigOdd.tobytes()
            )
        )

        # Readback pixel config
        readBackConfig = np.frombuffer(
            tpx4.ConfigGetPixels(
                rpc.ChipIndex(idx=helpers.cl_chip_idx())
            ).config,
            dtype=np.uint8
        )

        # Create 448 x 512 image
        config_image = tpx4tools.chip2logic_cfg_matrix(readBackConfig)

        # And show
        plt.imshow(config_image, vmin=0, vmax=63)
        plt.show()





