# Request progress, once per minute

The event scheduler prints one batch of active requests to stderr every 60 seconds.
Requests that finish sooner do not produce periodic output. Normal completion and
failure state saves remain immediate. No model calls are added by progress reporting.

Each line includes the call/task ID, elapsed time, time to HTTP response headers,
answer/reasoning character counts, and time since the most recent parsed stream
chunk. A response header is not a token; the output distinguishes waiting for
headers, waiting for the first chunk, and receiving chunks. Chunk timestamps track
SDK-delivered chunks, not raw network bytes or SSE keepalive comments.

Example (illustrative):

```text
[2026-11-19T16:01:00+00:00] extraction | running=2 queued=9
  CALL-000001 extract.0 | 等待响应 | 耗时 60s | 首响应 尚无 | 正文 0 字符 | 推理 0 字符 | 最近数据块 尚无数据块
  CALL-000002 extract.1 | 接收中 | 耗时 60s | 首响应 1.2s | 正文 8200 字符 | 推理 510 字符 | 最近数据块 2s前
```

The same snapshot is saved under `calls[].progress` in `state.json`, with
`progress_updated_at` marking the batch time. Completed calls remove that live
snapshot and retain their final counters/timestamps under `calls[].transport`.
Progress includes no prompts, answer text, reasoning text, or credentials.

The existing read-round budget, concurrency and transport I/O timeout are unchanged.
This adds no wall-clock deadline or retry. Changes take effect in a newly started
process; an already running process does not load the patch automatically.
