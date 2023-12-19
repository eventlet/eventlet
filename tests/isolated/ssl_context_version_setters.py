__test__ = False

if __name__ == "__main__":
    import eventlet
    eventlet.monkey_patch()
    import ssl

    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2

    print("pass")
