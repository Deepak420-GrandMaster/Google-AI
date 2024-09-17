# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from langchain_core.messages import HumanMessage

from app.server import app
from app.utils.input_types import InputChat

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a test client
client = TestClient(app)


@pytest.fixture
def sample_input_chat() -> InputChat:
    """
    Fixture to create a sample input chat for testing.
    """
    return InputChat(
        user_id="test-user",
        session_id="test-session",
        messages=[HumanMessage(content="What is the meaning of life?")],
    )


def test_redirect_root_to_docs() -> None:
    """
    Test that the root endpoint (/) redirects to the Swagger UI documentation.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert "Swagger UI" in response.text


class AsyncIterator:
    """
    A helper class to create asynchronous iterators for testing.
    """

    def __init__(self, seq: list) -> None:
        self.iter = iter(seq)

    def __aiter__(self) -> "AsyncIterator":
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self.iter)
        except StopIteration:
            raise StopAsyncIteration


@pytest.fixture
def mock_chain() -> Any:
    """
    Fixture to mock the chain object used in the application.
    """
    with patch("app.server.chain") as mock:
        yield mock


@pytest.mark.asyncio
async def test_stream_chat_events(mock_chain: Any) -> None:
    """
    Test the stream_events endpoint to ensure it correctly handles
    streaming responses and generates the expected events.
    """
    input_data = {
        "input": {
            "user_id": "test-user",
            "session_id": "test-session",
            "messages": [
                {"role": "user", "content": "Hello, AI!"},
                {"role": "ai", "content": "Hello!"},
                {"role": "user", "content": "What cooking recipes do you suggest?"},
            ],
        }
    }

    mock_uuid = "12345678-1234-5678-1234-567812345678"
    mock_events = [
        {"event": "on_chat_model_stream", "data": {"content": "Mocked response"}},
        {"event": "on_chat_model_stream", "data": {"content": "Additional response"}},
    ]

    mock_chain.astream_events.return_value = AsyncIterator(mock_events)

    with patch("uuid.uuid4", return_value=mock_uuid), patch(
        "app.server.Traceloop.set_association_properties"
    ):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/stream_events", json=input_data)

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    events = []
    for event in response.iter_lines():
        events.append(json.loads(event))

    assert len(events) == 4
    assert events[0]["event"] == "metadata"
    assert events[0]["data"]["run_id"] == str(mock_uuid)
    assert events[1]["event"] == "on_chat_model_stream"
    assert events[1]["data"]["content"] == "Mocked response"
    assert events[2]["event"] == "on_chat_model_stream"
    assert events[2]["data"]["content"] == "Additional response"
    assert events[3]["event"] == "end"
