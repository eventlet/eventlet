__test__ = False


class Foo:
    pass


if __name__ == '__main__':
    import eventlet.hubs
    eventlet.hubs.use_hub(Foo)
    hub = eventlet.hubs.get_hub()
    assert isinstance(hub, Foo), repr(hub)
    print('pass')
