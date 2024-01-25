# Copyright 2023 Google LLC

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

-- noqa: disable=PRS
CREATE OR REPLACE FUNCTION
  `${project_id}.${dataset_id}.${bq_function_name}`(gcs_uri STRING) RETURNS STRING
  REMOTE WITH CONNECTION `${project_id}.${region}.${bq_connection_id}`
  OPTIONS (
    endpoint = '${remote_function_url}',
    max_batching_rows = 1
  );
