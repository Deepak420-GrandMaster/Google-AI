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
from typing import Any, Dict, Generator
from urllib.parse import urljoin

import google.auth
import google.auth.transport.requests
import google.oauth2.id_token
import requests
from google.auth.exceptions import DefaultCredentialsError
from langchain_core.messages import AIMessage

import streamlit as st


@st.cache_resource()
class Client:
    """A client for streaming events from a server."""

    def __init__(self, url: str, authenticate_request: bool = False) -> None:
        """Initialize the Client with a base URL."""
        self.url = urljoin(url, "stream_events")
        self.authenticate_request = authenticate_request
        self.creds, _ = google.auth.default()

        if self.authenticate_request:
            self.id_token = self.get_id_token(self.url)

    def get_id_token(self, url: str):
        """
        Retrieves an ID token, attempting to use a service-to-service method first and
        otherwise using user default credentials.
        See more on Cloud Run authentication at this link:
         https://cloud.google.com/run/docs/authenticating/service-to-service
        Args:
            url: The URL to use for the token request.
        """

        auth_req = google.auth.transport.requests.Request()
        try:
            token = google.oauth2.id_token.fetch_id_token(auth_req, url)
        except DefaultCredentialsError:
            self.creds.refresh(auth_req)
            token = self.creds.id_token
        return token

    def log_feedback(self, feedback_dict, run_id):
        score = feedback_dict["score"]
        if score == "😞":
            score = 0.0
        elif score == "🙁":
            score = 0.25
        elif score == "😐":
            score = 0.5
        elif score == "🙂":
            score = 0.75
        elif score == "😀":
            score = 1.0
        feedback_dict["score"] = score
        feedback_dict["run_id"] = run_id
        feedback_dict["log_type"] = "feedback"
        feedback_dict.pop("type")
        url = urljoin(self.url, "feedback")
        headers = {
            "Content-Type": "application/json",
        }
        if self.authenticate_request:
            headers["Authorization"] = f"Bearer {self.id_token}"
        requests.post(url, data=json.dumps(feedback_dict), headers=headers)

    def stream_events(
        self, data: Dict[str, Any]
    ) -> Generator[Dict[str, Any], None, None]:
        """Stream events from the server, yielding parsed event data."""
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.authenticate_request:
            headers["Authorization"] = f"Bearer {self.id_token}"

        with requests.post(
            self.url, json={"input": data}, headers=headers, stream=True
        ) as response:
            for line in response.iter_lines():
                if line:
                    try:
                        event = json.loads(line.decode("utf-8"))
                        # print(event)
                        yield event
                    except json.JSONDecodeError:
                        print(f"Failed to parse event: {line.decode('utf-8')}")


class StreamHandler:
    """Handles streaming updates to a Streamlit interface."""

    def __init__(self, st, initial_text=""):
        """Initialize the StreamHandler with Streamlit context and initial text."""
        self.st = st
        self.tool_expander = st.expander("Tool Calls:", expanded=False)
        self.container = st.empty()
        self.text = initial_text
        self.tools_logs = initial_text

    def new_token(self, token: str) -> None:
        """Add a new token to the main text display."""
        self.text += token
        self.container.markdown(self.text, unsafe_allow_html=True)

    def new_status(self, status_update: str) -> None:
        """Add a new status update to the tool calls expander."""
        self.tools_logs += status_update
        self.tool_expander.markdown(status_update)


class EventProcessor:
    """Processes events from the stream and updates the UI accordingly."""

    def __init__(self, st, client, stream_handler):
        """Initialize the EventProcessor with Streamlit context, client, and stream handler."""
        self.st = st
        self.client = client
        self.stream_handler = stream_handler
        self.final_content = ""
        self.tool_calls = []
        self.tool_calls_outputs = []
        self.additional_kwargs = {}
        self.current_run_id = None

    def process_events(self):
        """Process events from the stream, handling each event type appropriately."""
        messages = self.st.session_state.user_chats[
            self.st.session_state["session_id"]
        ]["messages"]
        stream = self.client.stream_events(
            data={
                "messages": messages,
                "user_id": self.st.session_state["user_id"],
                "session_id": self.st.session_state["session_id"],
            }
        )

        event_handlers = {
            "metadata": self.handle_metadata,
            "end": self.handle_end,
            "on_tool_start": self.handle_tool_start,
            "on_tool_end": self.handle_tool_end,
            "on_retriever_end": self.handle_tool_end,
            "on_retriever_start": self.handle_tool_start,
            "on_chat_model_stream": self.handle_chat_model_stream,
        }

        for event in stream:
            event_type = event.get("event")
            handler = event_handlers.get(event_type)
            if handler:
                handler(event)

    def handle_metadata(self, event: Dict[str, Any]) -> None:
        """Handle metadata events."""
        self.current_run_id = event["data"].get("run_id")

    def handle_tool_start(self, event: Dict[str, Any]) -> None:
        """Handle the start of a tool or retriever execution."""
        msg = (
            f"\n\nCalling tool: `{event['name']}` with args: `{event['data']['input']}`"
        )
        self.stream_handler.new_status(msg)

    def handle_tool_end(self, event: Dict[str, Any]) -> None:
        """Handle the end of a tool execution."""
        data = event["data"]
        # Support tool events
        if isinstance(data["output"], dict):
            tool_id = data["output"].get("tool_call_id", None)
            tool_name = data["output"].get("name", "Unknown Tool")
        # Support retriever events
        else:
            tool_id = event.get("id", "None")
            tool_name = event.get("name", event["event"])

        tool_input = data["input"]
        tool_output = data["output"]

        tool_call = {"id": tool_id, "name": tool_name, "args": tool_input}
        self.tool_calls.append(tool_call)
        tool_call_outputs = {"id": tool_id, "output": tool_output}
        self.tool_calls_outputs.append(tool_call_outputs)
        msg = (
            f"\n\nEnding tool: `{tool_call['name']}` with\n **args:**\n"
            f"```\n{json.dumps(tool_call['args'], indent=2)}\n```\n"
            f"\n\n**output:**\n "
            f"```\n{json.dumps(tool_output, indent=2)}\n```"
        )
        self.stream_handler.new_status(msg)

    def handle_chat_model_stream(self, event: Dict[str, Any]) -> None:
        """Handle incoming tokens from the chat model stream."""
        data = event["data"]
        content = data["chunk"]["content"]
        self.additional_kwargs = {
            **self.additional_kwargs,
            **data["chunk"]["additional_kwargs"],
        }
        if content and len(content.strip()) > 0:
            self.final_content += content
            self.stream_handler.new_token(content)

    def handle_end(self, event: Dict[str, Any]) -> None:
        """Handle the end of the event stream and finalize the response."""
        additional_kwargs = self.additional_kwargs
        additional_kwargs["tool_calls_outputs"] = self.tool_calls_outputs
        final_message = AIMessage(
            content=self.final_content,
            tool_calls=self.tool_calls,
            id=self.current_run_id,
            additional_kwargs=additional_kwargs,
        ).model_dump()
        session = self.st.session_state["session_id"]
        self.st.session_state.user_chats[session]["messages"].append(final_message)
        self.st.session_state.run_id = self.current_run_id


def get_chain_response(st, client, stream_handler):
    """Process the chain response update the Streamlit UI.

    This function initiates the event processing for a chain of operations,
     involving an AI model's response generation and potential tool calls.
    It creates an EventProcessor instance and starts the event processing loop.

    Args:
        st (streamlit): The Streamlit app instance, used for accessing session state
                        and updating the UI.
        client (Client): An instance of the Client class used to stream events
                         from the server.
        stream_handler (StreamHandler): An instance of the StreamHandler class
                                        used to update the Streamlit UI with
                                        streaming content.

    Returns:
        None

    Side effects:
        - Updates the Streamlit UI with streaming tokens and tool call information.
        - Modifies the session state to include the final AI message and run ID.
        - Handles various events like chain starts/ends, tool calls, and model outputs.
    """
    processor = EventProcessor(st, client, stream_handler)
    processor.process_events()
