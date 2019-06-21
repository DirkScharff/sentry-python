import pytest

from sentry_sdk import Hub, capture_message
from sentry_sdk.tracing import Span


@pytest.mark.parametrize("sample_rate", [0.0, 1.0])
def test_basic(sentry_init, capture_events, sample_rate):
    sentry_init(traces_sample_rate=sample_rate)
    events = capture_events()

    with Hub.current.trace(transaction="hi"):
        with pytest.raises(ZeroDivisionError):
            with Hub.current.span(op="foo", description="foodesc"):
                1 / 0

        with Hub.current.span(op="bar", description="bardesc"):
            pass

    if sample_rate:
        event, = events

        span1, span2 = event["spans"]
        parent_span = event
        assert span1["tags"]["error"]
        assert span1["op"] == "foo"
        assert span1["description"] == "foodesc"
        assert not span2["tags"]["error"]
        assert span2["op"] == "bar"
        assert span2["description"] == "bardesc"
        assert parent_span["transaction"] == "hi"
    else:
        assert not events


@pytest.mark.parametrize("sampled", [True, False, None])
def test_continue_from_headers(sentry_init, capture_events, sampled):
    sentry_init(traces_sample_rate=1.0)
    events = capture_events()

    with Hub.current.trace(transaction="hi") as old_trace:
        old_trace.sampled = sampled
        with Hub.current.span() as old_span:
            headers = dict(Hub.current.iter_trace_propagation_headers())

    header = headers["sentry-trace"]
    if sampled is True:
        assert header.endswith("-1")
    if sampled is False:
        assert header.endswith("-0")
    if sampled is None:
        assert header.endswith("-")

    span = Span.continue_from_headers(headers)
    assert span is not None
    assert span.sampled == sampled
    assert span.trace_id == old_span.trace_id

    with Hub.current.trace(span):
        with Hub.current.configure_scope() as scope:
            scope.transaction = "ho"

        capture_message("hello")

    if sampled is False:
        message, = events
    else:
        trace1, message, trace2 = events

        assert trace1["transaction"] == "hi"
        assert trace2["transaction"] == "ho"

        assert (
            trace1["contexts"]["trace"]["trace_id"]
            == trace2["contexts"]["trace"]["trace_id"]
            == span.trace_id
            == message["contexts"]["trace"]["trace_id"]
        )

    assert message["message"] == "hello"