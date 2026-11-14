from src.interfaces.web.__main__ import build_parser, is_loopback, main


def test_defaults():
    a = build_parser().parse_args([])
    assert a.db == "data/index.db"
    assert a.host == "127.0.0.1"
    assert a.port == 8765
    assert not a.no_model and not a.allow_remote


def test_is_loopback():
    assert is_loopback("127.0.0.1") and is_loopback("::1") and is_loopback("localhost")
    assert not is_loopback("0.0.0.0") and not is_loopback("192.168.1.5")


def test_non_loopback_refused_without_flag(capsys):
    assert main(["--host", "0.0.0.0"]) == 2
    assert "Refusing" in capsys.readouterr().err
