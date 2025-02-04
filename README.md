# spidr4py library

This archive contains the release of the spidr4py library which contains the top level package spidr4. This package also contains the following sub-packages:

 * io - read access to the spidr4 data-acquisition (sdaq) file format
 * stream - support for acquiring tpx4 pixel data directly over slow control or 10 GBe without using a DAQ server.
 * rpc - Direct access to the gRPC stubs. See https://spidr4.nikhef.nl/docs/html/reference/grpc.html for the gRPC objects and messages. 
 * tpx4tools - support tools for tpx4 such as pixel coordinate translation functions, structures for disecting pixel packets and functions for which an easy gRPC stub does not exist. 
 * tpx4regs - contains constants for each timepix4 address.  

For examples of hows these work together, see the examples directory. 

## Requirements

 * python 3.7 or higher 
 * python 3.6 does not always work

## Contains

 * Installation:`spidr4py-<version>-py3-none-any.whl`
 * Examples: examples/` 

## Installation

```bash
$ pip3 install --user spidr4py-<version>-py3-none-any.whl`
```
Where you need to replace version with the correct version.

## Running the examples

Go into the examples directory.

To run the hello world example:

```bash
$ cd examples
$ python3 spidr4_helloworld.py 192.168.1.10
```
Where you need to replace `192.168.1.10` the IP with the IP of your spidr4 control board.

## Common problems

If you see an error similar to the following:

```
Traceback (most recent call last):
  File "/home/<user>/anaconda3/envs/spidr4/lib/python3.8/runpy.py", line 194, in _run_module_as_main
    return _run_code(code, main_globals, None,
  File "/home/<user>/anaconda3/envs/spidr4/lib/python3.8/runpy.py", line 87, in _run_code
    exec(code, run_globals)
  File "/home/<user>/projects/spidr4/manager/manager/__main__.py", line 2, in <module>
    from spidr4 import find
  File "/home/<user>/.local/lib/python3.8/site-packages/spidr4/find.py", line 8, in <module>
    from spidr4 import rpc
  File "/home/<user>/.local/lib/python3.8/site-packages/spidr4/rpc/__init__.py", line 4, in <module>
    from .common_pb2 import *
  File "/home/<user>/.local/lib/python3.8/site-packages/spidr4/rpc/common_pb2.py", line 28, in <module>
    _EMPTY = _descriptor.Descriptor(
  File "/home/<user>/.local/lib/python3.8/site-packages/google/protobuf/descriptor.py", line 313, in __new__
    _message.Message._CheckCalledFromGeneratedFile()
TypeError: Descriptors cannot not be created directly.
If this call came from a _pb2.py file, your generated code is out of date and must be regenerated with protoc >= 3.19.0.
If you cannot immediately regenerate your protos, some other possible workarounds are:
 1. Downgrade the protobuf package to 3.20.x or lower.
 2. Set PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python (but this will use pure-Python parsing and will be much slower).
```

it means you have protobuf both in your virtual environment and .local (or global) python installation. To fix this, remove the protobuf installation from your local environment such that only the one in the virtual environment can be found.


## Questions

Please contact me: v.van.beveren@nikhef.nl, or someone from the spidr4 team.

## License

See LICENSE
