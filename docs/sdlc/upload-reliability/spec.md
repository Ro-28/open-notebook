# Upload reliability specification

Root cause: repo_create converts string DB errors to RuntimeError but never retries. ObjectModel.save propagates it; HTTP upload has no worker retry boundary. Existing worker retries do not protect initial source persistence.

Ranked hypotheses: (1) missing retry on aborted insert predicts conflict-then-success fails at repository seam (confirmed by code and live trace); (2) permanent schema/validation failure predicts retry cannot help (negative tests); (3) transport/unknown commit outcome predicts unsafe replay (never retry these).

Retry only RuntimeError containing the database's explicit `Failed to commit transaction due to a read or write conflict` diagnostic. Maximum five operation attempts, asynchronous exponential jittered waits (50ms base, 1s cap). Normalize string errors inside the operation. Do not retry connection setup/cleanup, parsing, entire HTTP requests, command submission, or arbitrary multi-statement queries. Opt known single-statement repository writes into query retries; arbitrary repo_query remains non-retrying by default. Aborted transactions commit nothing, so retrying that atomic statement cannot duplicate a committed insert/edge. Permanent failures retain existing behavior.
