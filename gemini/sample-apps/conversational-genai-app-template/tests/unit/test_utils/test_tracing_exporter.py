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

from unittest.mock import Mock, patch

import pytest
from google.cloud import logging as google_cloud_logging
from google.cloud import storage
from opentelemetry.sdk.trace import ReadableSpan

from app.utils.tracing import CloudTraceLoggingSpanExporter


@pytest.fixture
def mock_logging_client() -> Mock:
    return Mock(spec=google_cloud_logging.Client)


@pytest.fixture
def mock_storage_client() -> Mock:
    return Mock(spec=storage.Client)


@pytest.fixture
def exporter(
    mock_logging_client: Mock, mock_storage_client: Mock
) -> CloudTraceLoggingSpanExporter:
    return CloudTraceLoggingSpanExporter(
        project_id="test-project",
        logging_client=mock_logging_client,
        storage_client=mock_storage_client,
        bucket_name="test-bucket",
    )


def test_init(exporter: CloudTraceLoggingSpanExporter) -> None:
    assert exporter.project_id == "test-project"
    assert exporter.bucket_name == "test-bucket"
    assert exporter.debug is False


def test_ensure_bucket_exists(exporter: CloudTraceLoggingSpanExporter) -> None:
    exporter.storage_client.bucket.return_value.exists.return_value = False
    exporter._ensure_bucket_exists()
    exporter.storage_client.create_bucket.assert_called_once_with("test-bucket")


def test_store_in_gcs(exporter: CloudTraceLoggingSpanExporter) -> None:
    span_id = "test-span-id"
    content = "test-content"
    uri = exporter.store_in_gcs(content, span_id)
    assert uri == f"gs://test-bucket/spans/{span_id}.json"
    exporter.bucket.blob.assert_called_once_with(f"spans/{span_id}.json")


@patch("json.dumps")
def test_process_large_attributes_small_payload(
    mock_json_dumps: Mock, exporter: CloudTraceLoggingSpanExporter
) -> None:
    mock_json_dumps.return_value = "a" * 100  # Small payload
    span_dict = {"attributes": {"key": "value"}}
    result = exporter._process_large_attributes(span_dict, "span-id")
    assert result == span_dict


@patch("json.dumps")
def test_process_large_attributes_large_payload(
    mock_json_dumps: Mock, exporter: CloudTraceLoggingSpanExporter
) -> None:
    mock_json_dumps.return_value = "a" * (400 * 1024 + 1)  # Large payload
    span_dict = {
        "attributes": {
            "key1": "value1",
            "traceloop.association.properties.key2": "value2",
        }
    }
    result = exporter._process_large_attributes(span_dict, "span-id")
    assert "uri_payload" in result["attributes"]
    assert "url_payload" in result["attributes"]
    assert "key1" not in result["attributes"]
    assert "traceloop.association.properties.key2" in result["attributes"]


@patch.object(CloudTraceLoggingSpanExporter, "_process_large_attributes")
def test_export(
    mock_process_large_attributes: Mock, exporter: CloudTraceLoggingSpanExporter
) -> None:
    mock_span = Mock(spec=ReadableSpan)
    mock_span.get_span_context.return_value.trace_id = 123
    mock_span.get_span_context.return_value.span_id = 456
    mock_span.to_json.return_value = '{"key": "value"}'

    mock_process_large_attributes.return_value = {"processed": "data"}

    exporter.export([mock_span])

    mock_process_large_attributes.assert_called_once()
    exporter.logger.log_struct.assert_called_once()
