import warnings

import six
from eventlet.green import httplib
from eventlet.zipkin import api


# see https://twitter.github.io/zipkin/Instrumenting.html
HDR_TRACE_ID = 'X-B3-TraceId'
HDR_SPAN_ID = 'X-B3-SpanId'
HDR_PARENT_SPAN_ID = 'X-B3-ParentSpanId'
HDR_SAMPLED = 'X-B3-Sampled'


def patch():
    if six.PY2:
        httplib.HTTPConnection.endheaders = _patched_endheaders
        httplib.HTTPResponse.begin = _patched_begin
    warnings.warn("Since current Python thrift release \
        doesn't support Python 3, eventlet.zipkin.http \
        doesn't also support Python 3 (http.client)")


def unpatch():
    if six.PY2:
        httplib.HTTPConnection.endheaders = __org_endheaders__
        httplib.HTTPResponse.begin = __org_begin__
    pass


def hex_str(n):
    """
    Thrift uses a binary representation of trace and span ids
    HTTP headers use a hexadecimal representation of the same
    """
    return '%0.16x' % (n,)
