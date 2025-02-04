from spidr4 import rpc
import helpers

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=False)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        # Get the services
        control = rpc.ControlInfoStub(channel)
        # shutdown the power.
        control.Shutdown(rpc.ShutdownRequest(action=rpc.ShutdownRequest.RESTART_SERVICE))
