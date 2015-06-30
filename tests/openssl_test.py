from tests import LimitedTestCase, main, SkipTest

class TestOpenSSL(LimitedTestCase):
    def test_import(self):
        try:
            import OpenSSL
        except:
            raise SkipTest("need OpenSSL")

        # Ensure that it's possible to import eventlet.green.OpenSSL.
        # Most basic test to check Python 3 compatibility.
        import eventlet.green.OpenSSL.SSL
        import eventlet.green.OpenSSL.crypto
        import eventlet.green.OpenSSL.rand
        import eventlet.green.OpenSSL.tsafe
        import eventlet.green.OpenSSL.version


if __name__ == '__main__':
    main()
