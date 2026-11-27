import socket

from app.monitoring import probes


def test_tcp_probe_succeeds_when_something_is_listening():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        assert probes.probe(f"tcp://127.0.0.1:{port}") is True


def test_tcp_probe_fails_when_nothing_is_listening():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # the socket is closed now, so the port is free and refuses connections
    assert probes.probe(f"tcp://127.0.0.1:{port}") is False


def test_no_probe_possible_returns_none():
    assert probes.probe(None) is None
    assert probes.probe("/healthz") is None



def test_localhost_is_converted_to_ipv4_loopback():
    assert probes.to_ipv4_loopback("tcp://localhost:22001") == "tcp://127.0.0.1:22001"
    assert probes.to_ipv4_loopback("http://localhost:22000/_healthz") == "http://127.0.0.1:22000/_healthz"
    assert probes.to_ipv4_loopback("tcp://cartservice:7070") == "tcp://cartservice:7070"