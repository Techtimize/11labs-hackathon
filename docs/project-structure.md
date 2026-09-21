# Project structure

How the code is laid out, which layer may depend on which, and where new code goes.
`tests/architecture/test_boundaries.py` enforces the dependency rules below, so a change
that breaks one fails CI.

## Tree

```
authrelay/
├── main.py                     builds the app, opens the store, mounts the routers
│
├── api/                        HTTP entry points
│   ├── dependencies.py         composition root
│   ├── ratelimit.py            per-client rate limiting
│   ├── templating.py           Jinja environment
│   ├── templates/              call.html, review.html
│   └── v1/
│       ├── tools.py            the six agent tools
│       ├── call.py             call page, signed session URL
│       ├── review.py           reviewer queue, decision, audit trail
│       ├── webhooks.py         ElevenLabs post-call webhook
│       └── health.py
│
├── core/config.py              environment settings
│
├── database/
│   ├── connection.py           SQLite connection and its lock
│   ├── store.py                the concrete PreauthStore
│   ├── models/schema.py        tables, index, append-only triggers
│   └── repositories/           session, case, review, transcript, audit
│
├── dto/
│   ├── request/                tool and decision request bodies
│   └── common/                 Tier, Blocker, BlockerReport, Catalogue
│
├── interfaces/                 protocols the services depend on
│   ├── store.py                PreauthStore: the five repositories as one dependency
│   ├── *_repository.py         one per table
│   ├── conversation_sessions.py
│   └── record.py               a row readable by column name
│
├── services/                   use cases
│   ├── preauthorisation.py     the six agent tools
│   ├── review.py               queue, decision, audit trail
│   └── transcript.py           storing a post-call transcript
│
├── policies/                   decisions, all pure
│   ├── preauthorisation.py     blockers, tiers, policy version by service date
│   ├── similarity.py           similar earlier cases
│   ├── grounding.py            rule IDs spoken but never returned
│   └── tool_scope.py           which workflow node may use which tool
│
├── mapper/                     record and DTO to response shape
├── integrations/
│   ├── elevenlabs/client.py    signed session URL
│   └── fixtures/catalogue.py   synthetic cases, providers, policies
├── security/                   bearer tokens, page token, webhook signature
├── errors/                     exceptions, stable error codes, HTTP conversion
├── utils/normalise.py          reference normalisation
│
├── agent/  data/  scripts/     ElevenLabs config, fixture data, tooling
└── tests/
    ├── unit/                   pure: no store, no HTTP
    ├── integration/            services on a real SQLite store; HTTP via TestClient
    └── architecture/           the dependency rules
```

## What each folder is for

| Folder | Holds | Does not hold |
|---|---|---|
| `api/` | Routes. Parse the body, resolve auth and dependencies, call one service, return its result. | Queries, workflows, shaping records into responses |
| `api/dependencies.py` | The only place that names a concrete store or client. | Business logic |
| `core/` | Settings read from the environment. | Anything that changes at runtime |
| `database/` | SQL, the schema, the connection. | Decisions about what the data means |
| `dto/` | Plain data shapes shared across layers. | Behaviour, imports from other layers |
| `interfaces/` | Protocols for persistence and the voice platform. | Implementations |
| `services/` | One function per use case, coordinating the layers below. | SQL, HTTP, concrete classes |
| `policies/` | Pure decisions: same input, same answer. | I/O of any kind |
| `mapper/` | Converting one shape to another. | Fetching, deciding, side effects |
| `integrations/` | Code that talks to something outside this service. | Decisions about the result |
| `security/` | Checking who is calling. | Deciding what they may do with a case |
| `errors/` | Exceptions, error code strings, error to status mapping. | |

## Dependency direction

```
main ──> api ──> services ──> policies ──> dto
          │         │   └──> mapper   ──> dto
          │         └──────> interfaces
          │
          └──> api/dependencies ──> database ──────> interfaces, dto
                                └─> integrations ──> interfaces, dto
```

Each layer may import only these internal packages:

| Layer | May import |
|---|---|
| `main` | api, core |
| `api` | api, services, dto, security, errors, core |
| `api/dependencies.py` | the above, plus database, integrations, interfaces |
| `services` | interfaces, dto, policies, mapper, errors, utils |
| `policies` | dto, interfaces, errors |
| `mapper` | dto, and `interfaces.record` only |
| `dto` | dto |
| `interfaces` | interfaces, dto |
| `database` | database, interfaces, dto |
| `integrations` | interfaces, dto, core |
| `security` | core, errors |
| `errors`, `core` | themselves |
| `utils` | nothing |

Three more rules are checked:

- `sqlite3` is imported only in `database/`, and `httpx` only in `integrations/`.
- `services`, `policies`, `mapper`, `dto`, `interfaces`, `database`, `integrations`, `core` and
  `utils` never import FastAPI or Starlette.
- Nothing outside `database/` calls `.execute()`.

Two choices differ from a stricter reading:

- `api` may read `core.config`. The webhook route needs the signing secret, and passing one
  string through the composition root would add a dependency for nothing.
- `security` imports FastAPI. The bearer and page-token checks are FastAPI dependencies; they
  guard the transport, so they belong to it.

## A request, end to end

`POST /tools/send_to_review`, the hand-off to a human reviewer:

```
api/v1/tools.py              t_review(b: ReviewIn, store: StoreDep)
  dto/request/tools.py         ReviewIn validates the body; unknown fields are rejected
  security/auth.py             agent_auth checks the agent token
  api/dependencies.py          StoreDep supplies the store as a PreauthStore
services/preauthorisation.py send_to_review(store, ...)
  policies/preauthorisation.py find_blockers(): blockers and the minimum tier
  policies/similarity.py       similar_cases() over rows the repository fetched
  interfaces/store.py          PreauthStore is all the service knows about storage
database/store.py            Store hands each call to the repository that owns the table
  database/repositories/review.py   open_review_for, create_review
  database/models/schema.py         review_item, one open item per request by index
mapper/blocker.py            report_to_dict() shapes the report for the response
api/v1/tools.py              returns the service's dict
```

The service never learns that storage is SQLite, and the route never sees a row.

## Adding something

**A new agent tool.**
1. Request body in `dto/request/tools.py`.
2. Any new decision as a pure function in `policies/`.
3. The use case in `services/preauthorisation.py`, taking `store: PreauthStore`.
4. The route in `api/v1/tools.py`, with `agent_auth` and `tool_limit`.
5. The name in `policies/tool_scope.py` and the definition in `agent/tools.json`. A unit test
   fails if those two disagree.
6. New error codes in `errors/error_codes.py`, never inline.

**A new table.** DDL in `database/models/schema.py`, a repository in
`database/repositories/`, a protocol in `interfaces/`, then add the protocol to `PreauthStore`
and the delegating methods to `database/store.py`.

**A new external system.** Client in `integrations/<system>/client.py`, protocol in
`interfaces/`, construction in `api/dependencies.py`. Tests replace it with
`app.dependency_overrides`.

**A new test.** `tests/unit/` if it needs neither a store nor a client, otherwise
`tests/integration/`.

## Known gaps

- Responses are plain dicts, not response DTOs. The wire format was kept byte-identical
  through the restructure, and typing it would mean a second pass.
- `database/models/` holds DDL, not ORM classes. There is no ORM.
- No migrations. Tables are created with `CREATE ... IF NOT EXISTS` at startup, so a column
  change needs a migration tool first.
- `database/store.py` delegates about twenty methods by hand. It keeps every service call site
  unchanged; splitting services to take individual repositories would remove it.
- `tests/integration/test_api.py` sets its environment before importing `main`, because
  settings are read once at import. Running it after another test that imports `core.config`
  in the same process would break it. The architecture tests use `ast` so they never trigger
  this.
