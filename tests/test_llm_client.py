import pytest

from recovery_ledger.llm.client import MockLLMClient, OllamaClient, build_default_client


def test_mock_client_returns_default_response():
    client = MockLLMClient(default_response="hello")
    assert client.complete("anything") == "hello"


def test_mock_client_matches_keyed_responses():
    client = MockLLMClient(
        default_response="fallback",
        responses={"promise_to_pay": "PROMISE_TO_PAY", "opt_out": "OPT_OUT"},
    )
    assert client.complete("customer said please opt_out me") == "OPT_OUT"
    assert client.complete("something unrelated") == "fallback"


def test_mock_client_records_calls():
    client = MockLLMClient()
    client.complete("first", system="sys prompt", temperature=0.2)
    client.complete("second")
    assert len(client.calls) == 2
    assert client.calls[0] == {"prompt": "first", "system": "sys prompt", "temperature": 0.2}


@pytest.fixture
def ollama_client() -> OllamaClient:
    client = OllamaClient()
    if not client.is_available():
        pytest.skip("Ollama not running locally — skipping real-backend test")
    return client


def test_ollama_client_completes_a_real_prompt(ollama_client):
    reply = ollama_client.complete("Reply with exactly the word: PONG")
    assert isinstance(reply, str)
    assert len(reply) > 0


def test_ollama_unavailable_raises_clear_error():
    from recovery_ledger.llm.client import OllamaUnavailableError

    unreachable = OllamaClient(host="http://localhost:1", timeout_seconds=1.0)
    with pytest.raises(OllamaUnavailableError):
        unreachable.complete("hello")


def test_build_default_client_returns_something_usable():
    client = build_default_client()
    reply = client.complete("Reply with exactly the word: PONG")
    assert isinstance(reply, str)
    assert len(reply) > 0
