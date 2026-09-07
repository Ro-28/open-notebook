# Upload reliability intent

Concurrent multipart upload reproduction recorded 10 requests at concurrency 5, including four HTTP 500 responses. The reported trace fails inside repo_create on an explicitly aborted SurrealDB transaction (read/write conflict).

Constraints: backend repository/tests only; no frontend/launcher changes, service restart, commits, credentials, or production data/log test writes. Existing live API remains available. Success: deterministic tests prove bounded retries of aborted operations, no replay of successful operations, and immediate failure for ambiguous/permanent errors. Live post-restart reproduction belongs to the parent operator.
