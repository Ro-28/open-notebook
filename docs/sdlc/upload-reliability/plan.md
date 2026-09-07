# Upload reliability implementation plan

1. Write/run a failing repo_create regression at the DB operation seam using the exact captured diagnostic, including returned-string and raised-error forms.
2. Add a bounded async retry helper around individual database operations only; run GREEN.
3. Cover known single-statement writes (relate/update/upsert) via explicit repo_query opt-in; leave arbitrary queries untouched. Cover limits, backoff, cancellation, permanent/ambiguous failures, cleanup failure, and concurrent distinct inserts.
4. Run isolated backend tests and lint from a temporary CWD with dotenv disabled and test-only database configuration; never import the API from production CWD for tests.
5. Record red/green commands and evidence in data/app/upload-fix-report.md. Hand off ready-for-restart status without restarting.
