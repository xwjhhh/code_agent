import json
from contextlib import contextmanager

from code_agent.memory.embedding import SiliconFlowEmbeddingClient, SiliconFlowEmbeddingConfig


def test_siliconflow_embedding_request_uses_documented_endpoint_and_payload(monkeypatch):
    captured = {}

    class Response:
        def read(self):
            return json.dumps(
                {"data": [{"index": 0, "embedding": [0.1, 0.2]}, {"index": 1, "embedding": [0.3, 0.4]}]}
            ).encode("utf-8")

    @contextmanager
    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        yield Response()

    monkeypatch.setattr("code_agent.memory.embedding.urlopen", fake_urlopen)
    client = SiliconFlowEmbeddingClient(
        SiliconFlowEmbeddingConfig(
            api_key="test-key",
            model="Qwen/Qwen3-Embedding-0.6B",
            api_base="https://api.siliconflow.cn/v1",
            dimensions=1024,
        )
    )

    vectors = client.embed(["first", "second"])

    assert captured["url"] == "https://api.siliconflow.cn/v1/embeddings"
    assert captured["payload"] == {
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "input": ["first", "second"],
        "encoding_format": "float",
        "dimensions": 1024,
    }
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
