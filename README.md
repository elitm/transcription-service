# Transcription Service

Upload an audio or video file, get a transcription back in the file's original language.
The API accepts the upload immediately (`202 Accepted`), transcribes in the background with
[faster-whisper](https://huggingface.co/Systran/faster-whisper-base) and exposes the result
through a status endpoint and a Server-Sent Events stream.

Stack: FastAPI, SQLAlchemy + PostgreSQL, Pydantic, pytest, Docker Compose.

## Running

Prerequisites: Docker Desktop. The first start downloads the Whisper `base` model (~150 MB).

```bash
docker-compose up --build
```

This starts PostgreSQL (port 5432) and the API (port 8000). Swagger UI: http://localhost:8000/docs

Upload a file. macOS / Linux:

```bash
curl -X POST http://localhost:8000/jobs -F "file=@audio.mp3"
```

Windows PowerShell (`curl` there is an alias of `Invoke-WebRequest`, so call the real binary):

```powershell
curl.exe -X POST http://localhost:8000/jobs -F "file=@C:\path\to\audio.mp3"
```

```json
{"job_id": "adbd8a76-05f8-48f9-8586-63ce46765710"}
```

Poll the job:

```bash
curl http://localhost:8000/jobs/adbd8a76-05f8-48f9-8586-63ce46765710
```

```json
{
  "id": "adbd8a76-05f8-48f9-8586-63ce46765710",
  "status": "completed",
  "created_at": "2026-11-12T14:37:59.230198",
  "started_at": "2026-11-12T14:37:59.375630",
  "completed_at": "2026-11-12T14:38:02.475612",
  "language_detected": "he",
  "result": {"text": "...", "language": "he"},
  "error": null,
  "original_filename": "interview.mp3",
  "file_size_bytes": 433005
}
```

Or subscribe to live updates instead of polling:

```bash
curl -N http://localhost:8000/jobs/adbd8a76-05f8-48f9-8586-63ce46765710/subscribe
```

```
data: {"status": "processing"}

data: {"status": "completed", "text": "...", "language": "he"}
```

Stop everything with `docker-compose down`; add `-v` to also delete the database volume.

## API

| Method | Path | Response |
|--------|------|----------|
| `POST` | `/jobs` (multipart `file`) | `202` `{"job_id"}` · `400` unsupported type · `503` queue full |
| `GET` | `/jobs/{id}` | `200` job record · `404` |
| `GET` | `/jobs/{id}/subscribe` | `200` `text/event-stream` · `404` |

Job states: `queued → processing → completed | failed`, plus `interrupted` for jobs cut off
by a shutdown. Transitions are validated in `JobService`.

## Testing

Tests run against a real PostgreSQL database (`transcription_test`, created automatically),
so what passes in tests is what runs in production.

Inside Docker, same image and driver as production, includes the real faster-whisper tests:

```bash
docker-compose --profile test run --build --rm tests
```

For a faster loop from the IDE, with only the database in Docker:

```bash
docker-compose up -d postgres
python -m pytest
```

The test suite covers the queue, the job state machine, the SSE broadcaster, file storage, and
the HTTP API end to end: real app, real asyncio worker, PostgreSQL, with the Whisper model
replaced by a fake transcriber behind the `Transcriber` protocol.

## Design decisions

### File type validation

Accepted extensions: `mp3`, `wav`, `m4a`, `mp4`, `mov`. The check is done on the filename
extension before the file is written to disk, so bad uploads fail fast with `400`. Extension
checks are enough to stop accidental misuse; they do not stop a renamed file. If that matters,
sniffing the container with `ffprobe` is the next step; ffmpeg is already in the image.
Non-media content that slips through fails inside Whisper and the job ends as `failed` with
the error message stored.

### SSE with a single subscriber per job

SSE was chosen over WebSockets because updates only flow server → client, SSE works with
plain `curl` and `EventSource`, and it needs no extra protocol handling.

Each job allows one subscriber at a time. The broadcaster keeps one in-memory queue per job,
which keeps delivery simple and makes "who is listening" unambiguous. A second subscriber gets
an `error` event. Clients that need several listeners can poll `GET /jobs/{id}`.

Stream behaviour: subscribing to a finished job returns its final status immediately and
closes; otherwise the stream ends after the terminal event. Every 15 s without events the
server re-reads the job from the database and emits a `: keep-alive` comment, which also
covers the case where the job finished in the instant between the status check and the
subscription being registered.

### Transcription model: faster-whisper (`base`)

The assignment asks for an open-source Hugging Face model. `faster-whisper` is OpenAI's Whisper
re-implemented on CTranslate2: the same weights and accuracy, several times faster on CPU and
with a much smaller memory footprint, which matters because this service runs on CPU inside
Docker. Whisper detects the language itself and the text is returned untranslated, which gives
the "original language" requirement for free. `base` is the speed/accuracy trade-off for an MVP;
`WhisperTranscriber(model_size=...)` switches to `small`, `medium` or `large-v3`.

The model sits behind the `Transcriber` protocol, so tests use a fake and a different engine
could be dropped in without touching the API or the worker.

### In-process worker and in-memory queue

Transcription takes seconds to minutes, so the upload handler only stores the file, creates
the job row and enqueues the job id. A single background asyncio task, started and stopped in the
FastAPI lifespan, pulls ids from a FIFO queue (`JobQueue`, max depth 100) and runs the pipeline:
mark `processing` → transcribe (in a thread via `asyncio.to_thread` so blocking Whisper calls do not
starve other async tasks) → mark `completed`/`failed` → publish the SSE event. When the queue is
full the upload returns `503` instead of accepting work it cannot schedule.

Why this and not Celery/RQ: one process, one container, no broker to operate, and the
assignment's scale does not need horizontal workers. What it costs: the queue lives in memory,
so jobs still `queued` when the container restarts are not picked up again, and throughput is
one transcription at a time (Whisper on CPU is CPU-bound anyway, so a second thread would not
help much). The `JobQueue` and `QueueWorker` seams are where a Redis queue or a separate worker
process would plug in.

### PostgreSQL

Jobs are persisted in PostgreSQL through SQLAlchemy (`JobRepository`). The database is created
with `UTF8` encoding and the JSON result column is serialised with `ensure_ascii=False`, so
Hebrew and other non-Latin transcriptions are stored and readable as-is rather than as `א`
escapes. The driver is `psycopg` 3. Tables are created on startup (`create_all`); a migration
tool such as Alembic was left out for the MVP.

### No authentication

The API has no authentication or rate limiting. It is meant to run inside a trusted network or
behind a gateway that provides both. Adding an API key or JWT dependency to the routers is
straightforward and was out of scope for the time available.

### Local media storage

Uploads are written to `/uploads/{job_id}` on a Docker volume and referenced by path from the
job row. Object storage (S3/GCS) was skipped for time; `FileStorage` is the single place to
change. Files are kept after transcription (no retention policy yet).

## Assumptions

- Files small enough to be read into memory on upload (no streaming to disk, no size limit).
- The caller keeps the `job_id`; there is no list endpoint.
- Results are returned in the spoken language; translation is not a goal.
- Jobs in flight when the service stops are not resumed. On shutdown the worker gets a 5 s
  grace period to finish the current transcription; after that the in-flight job and every job
  still in the queue are marked `interrupted` (the client can re-upload). The queue itself is
  in memory, so a hard kill (no shutdown signal) leaves those rows as `queued`/`processing`.
- The worker and the API share one process, so the SSE subscriber lives in the API event loop
  and the worker publishes to it thread-safely; a multi-process setup would need an external
  pub/sub (e.g. PostgreSQL `LISTEN/NOTIFY` or Redis).

## Project layout

```
app/
  main.py                      create_app() factory, routes, lifespan, worker thread
  models/job.py                SQLAlchemy Job model
  schemas/transcription.py     Pydantic TranscriptionResult
  data/job_repository.py       PostgreSQL access
  infrastructure/job_queue.py  thread-safe FIFO with max depth
  services/
    job_service.py             state machine
    queue_worker.py            dequeue → transcribe → persist → broadcast
    event_broadcaster.py       SSE fan-out, one subscriber per job
    file_storage.py            upload persistence and extension validation
    transcriber.py             Transcriber protocol
    whisper_transcriber.py     faster-whisper implementation
tests/
  unit/                        queue, state machine, broadcaster, storage, transcriber
  integration/                 HTTP API end to end, real-model tests
  fakes/                       FakeTranscriber, BlockingTranscriber
```
