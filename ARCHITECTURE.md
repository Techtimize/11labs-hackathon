# AuthRelay

Synthetic data only.

## The problem

A clinic submits a pre-authorisation request through eClaimLink. It stalls, usually because a
document is missing or a diagnosis code doesn't match the procedure. The clinic's approval staff
then chase the insurer through portals, email and phone while the patient waits. Dubai's rules give
the payer six hours to decide an outpatient request and twenty-four for inpatient, and a
clarification loop eats most of that.

AuthRelay is a phone line the clinic calls. The agent works out what is blocking the request,
collects what's missing on the call, and hands a complete case to a qualified reviewer.

It never approves or denies anything. That is not a policy, it is the shape of the code: no tool
the agent can reach writes a decision.

## The call

Five nodes, each with only the tools it needs.

| Node | What it does | Tools |
|---|---|---|
| 1 Disclosure | States it is the insurer's AI, that the call is recorded, and that people decide | none |
| 2 Verify | Facility ID and request reference, read back and confirmed | `verify_session` |
| 3 Diagnose | Names the blocker with its rule ID and policy version | `get_case_blockers` |
| 4 Resolve | Takes the missing document reference, rechecks | `record_evidence_reference`, `recheck_case` |
| 5 Hand off | Reads back the review reference | `send_to_review`, `transfer_to_human` |

From any node: "human" or "stop" transfers the call, a clinical question goes to tier 2, and two
tool timeouts end in a transfer rather than a guess.

## The three zones

**Caller.** A clinic approval executive on a web page using the ElevenLabs Web SDK. Telephony
through Twilio or SIP is the production path. The clinic's HIS or EMR is not touched.

**ElevenLabs.** Scribe v2 for speech, with keyterms for CPT and ICD codes and Arabic insurance
vocabulary. The Agents Platform runs the conversation on a model chosen in-platform. Agent
Workflows enforce the node order and scope the tools. Eleven v3 speaks the answer in English or
Arabic. Agent Testing runs the scenarios.

**Control plane.** A FastAPI service with no LLM in it and no model keys. It checks eligibility,
completeness and coding with plain functions, holds the case and audit store, and serves the
reviewer queue. Every tool call is authorised against the provider and case the call is bound to.

The LLM talks. The control plane decides what is true. A person decides what happens.

## Real and synthetic

Real: the six tools, the rules engine, the policy versioning, the reviewer queue and its human gate,
the audit store, webhook signature verification.

Synthetic: the case store, the payer adapter, the eClaimLink adapter, and all eight cases and three
providers in `data/`. Responses carry an `X-Data-Mode: synthetic` header.

Not built: OCR, MCP, batch calling, agent-to-agent dialling. Urdu is evaluated, not shipped.

## Rules

`policies/preauthorisation.py` is pure functions over the standard library. Same inputs, same
result, so any tier in the audit log can be recomputed from it.

A policy version is selected by the service date, not by today's date, so a case from June is
checked against June's rules. Blockers come back in five kinds: `MISSING_DOC`, `CODE_MISMATCH`,
`ELIGIBILITY`, `POLICY_AMBIGUITY`, `CLINICAL`.

Tiers follow from the blockers:

- **Tier 0** everything resolvable on the call
- **Tier 1** something that isn't, like an eligibility conflict or a code mismatch
- **Tier 2** clinical review, or a procedure not in the schedule of benefits

The agent may raise a tier. It cannot lower one. `send_to_review` takes the higher of what the agent
asked for and what the rules require.

## Guardrails and where they live

Each of these is a mechanism, not an instruction in a prompt.

| Requirement | How it holds | Where |
|---|---|---|
| No AI decision | No agent tool writes a decision. `decide` needs the reviewer token and a stored transcript | `services/review.py`, `policies/tool_scope.py` |
| One case per call | The session binds to one request at verification; anything else is refused and audited | `services/preauthorisation.py` `_scoped` |
| One decision per request | Partial unique index on undecided items. A repeated hand-off returns the item already waiting | `database/models/schema.py` |
| Tier floor | `send_to_review` takes the maximum of requested and required | `services/preauthorisation.py` |
| Opt-out | `transfer_to_human` is reachable from every node | `policies/tool_scope.py` |
| Callback consent | Written to the session row and read back before anything is arranged | `services/preauthorisation.py` |
| Audit | `audit_event` rejects UPDATE and DELETE by trigger. Every tool call writes a row under its own name | `database/models/schema.py` |
| Verification without secrets | Facility ID and request reference only. Two attempts, then locked | `services/preauthorisation.py` |
| Session minting | `/session/signed-url` needs a short-lived page token and is rate limited | `security/page_token.py`, `api/v1/call.py` |
| Reviewer page | Rows built with DOM methods, so an agent-written summary can never become markup | `api/templates/review.html` |

Two credentials, never interchangeable. `AGENT_TOOL_TOKEN` reaches `/tools/*`. `REVIEWER_TOKEN`
reaches `/review/*` and `/audit/*`.

## Post-call

ElevenLabs posts the transcript to `/webhooks/elevenlabs/post-call`. The signature is checked
against a 30-minute window and redelivery is ignored. A reviewer cannot sign off until that
transcript is stored, so no decision exists without the conversation that produced it.

`policies/grounding.py` compares the rule IDs the agent spoke against the ones the tools actually
returned. Anything it said that no tool gave it shows up.

## Layout

```
main.py     builds the app and mounts the routers
api/        routes and the composition root
services/   use cases: the six tools, the reviewer's decision
policies/   the rules engine, tiers, similar cases
database/   SQLite schema, repositories, append-only audit
interfaces/ what the services depend on, as protocols
agent/      tools.json, system prompt, workflow, test scenarios, keyterms
data/       synthetic cases and policies
tests/      86 tests: unit, integration, architecture
```

Services, policies and the database layer import no web framework, and no service knows the store
is SQLite. Guardrails are testable without a server or a voice call. The full tree and the layer
rules are in [docs/project-structure.md](docs/project-structure.md).

## Running it

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements-dev.txt
cp .env.example .env          
uvicorn main:app --env-file .env --reload
```

`/health` for status, `/docs` for the API, `/` for the call page, `/review` for the queue.

Before connecting the agent, point the tools at the deployment:

```bash
python scripts/set_tool_host.py https://your-host.example.com
```

## Tests

86 tests, lint and types clean. `python -m unittest discover -s tests -t . -v`

10 unit tests cover the pure pieces, 69 integration tests run every use case on a real SQLite store
and over HTTP, and 7 architecture tests hold the layer boundaries. They run in CI on every push
alongside ruff and mypy.

The ones worth reading are the adversarial ones: a request cannot be approved and denied, the agent
cannot lower a tier, a verified call cannot reach another case, a decision cannot precede its
transcript, a forged page token is refused.

## Known limits

The reviewer name recorded against a decision is self-declared behind a shared token. SSO is the
production step.

Consent for a callback starts as a flag the agent sets from what the caller said. What the code
enforces is that nothing is arranged unless that consent is stored and read back. The recording is
the evidence.

SQLite with one serialised connection. Postgres swaps in behind `database/` without touching the
tools.

## Next

Platform work from 30 September: the workflow and prompt into the Agents Platform, voices and
keyterms, S1 to S10 in Agent Testing at five runs each, Arabic on S6, and a load test against the
tool endpoints.
