import sys

try:
    from zmq import FORWARDER, PUB, SUB, SUBSCRIBE
    from zmq.devices import Device
except ModuleNotFoundError:
    raise SystemExit("Unable to find required zmq module. "
                     "Please install it before running this example.")


if __name__ == "__main__":
    usage = 'usage: chat_bridge sub_address pub_address'
    if len(sys.argv) != 3:
        print(usage)
        sys.exit(1)

    sub_addr = sys.argv[1]
    pub_addr = sys.argv[2]
    print("Recieving on %s" % sub_addr)
    print("Sending on %s" % pub_addr)
    device = Device(FORWARDER, SUB, PUB)
    device.bind_in(sub_addr)
    device.setsockopt_in(SUBSCRIBE, "")
    device.bind_out(pub_addr)
    device.start()
