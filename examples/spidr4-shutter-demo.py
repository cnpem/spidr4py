import time

from spidr4 import rpc
import helpers

if __name__ == '__main__':
    # Parse command-line
    ns = helpers.cl_parse(with_chip_idx=False)

    # Main loop, create network connection
    with helpers.cl_connect() as channel:
        trigger = rpc.TriggerStub(channel)              # Get the control service
        trigger.Enable(rpc.EMPTY)                       # Enable the trigger logic block
        trigger.StopAutoShutter(rpc.EMPTY)              # Just in case it was still running

        trigCfg = rpc.TriggerConfig(    # Configure the trigger using the internal auto-shutter
            shutter_input=rpc.SHUTTER_IN_AUTO_GEN,      # Shutter mode auto-generate, start on software
            t0_input=rpc.T0SYNC_IN_SOFTWARE,            # T0 sync also by software
            busy_output=rpc.BUSY_OUT_SHUTTER,           # Show shutter signaal on busy-out
            auto_shutter_open_us=250,                   # Open shutter for 250 us
            auto_shutter_close_us=750,                  # Close shutter for 750 us
            shutter_count=2000                          # Generate 2000 shutters
        )
        trigger.SetConfig(trigCfg)
        trigger.ResetShutterCounter(rpc.EMPTY)          # Reset shutter counter
        trigger.ResetT0Counter(rpc.EMPTY)               # Reset T0 counter

        trigger.StartAutoShutter(rpc.EMPTY)             # Start auto-shutter

        status = trigger.GetStatus(rpc.EMPTY)           # Wait until it is done
        while status.auto_shutter_busy:
            time.sleep(0.1)
            trigger.T0Sync(rpc.EMPTY)                   # Generate a t0 sync
            status = trigger.GetStatus(rpc.EMPTY)       # Get the current status
            print(f"Shutter count: {status.shutter_counter}")
            print(f"T0-sync count: {status.t0sync_counter} (should be ~1/100th of shutter_counter)")

