from spidr4 import rpc
import helpers

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=False)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:

        # Get the control service
        control = rpc.ControlInfoStub(channel)

        # Restart the spidr4 device
        control.Shutdown(rpc.ShutdownRequest(action=rpc.ShutdownRequest.ShutdownAction.RESET))
