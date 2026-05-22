# Design Note — Agent Memory Evolution: Context Compaction & PDPA Erasure

- **Status:** Draft / Proposed
- **Date:** 2026-05-22
- **Scope:** `src/swarm_engine/overseer.rs`, `src/memory/memvid_manager.rs`, `src/memory/tool.rs`
- **Related:** session checkpoint (`swarm_checkpoints`), Memvid `.mv2` capsules

---

## 1. Background — current memory architecture

Bifrost today uses a **two-layer "Persistent Multi-Layer Recall"** design with
no summarization or compression:

| Layer | Where | Behaviour |
|-------|-------|-----------|
| **Short-term** | `swarm_checkpoints.state_json` (MariaDB) | Full conversation history as JSON array, upserted every turn (`ON DUPLICATE KEY UPDATE`). Scoped `{patient_id}:{session_id}` + tenant. **Loaded in full every turn** — no truncation. |
| **Long-term** | `.mv2` capsule per `agent_{id}_session_{id}` (`MemvidManager`) | Each turn appends an immutable "Smart Frame" via `commit_memory()`. Recall via `search_memory()` (`SearchEngineKind::LexFallback`, top_k=5, 200-char snippets). |
| **Per-turn retrieval** | Vector (Qdrant) / Graph (Neo4j) / Tree (PageIndex) / Memvid | Merged into `manual_context` and injected into the prompt. |

This prioritises **recall fidelity + auditability** over token economy — a
deliberate fit for clinical/regulated workloads. It carries two known costs this
note addresses.

---

## 2. Problem A — context cost & the hard context-window wall

Because history is loaded in full every turn:

- **Token cost grows linearly** with conversation length → unbounded per-turn
  cost on paid models (interacts with the per-tenant oracle/cloud budget cap).
- **No graceful degradation:** there is no token budget guard. When the prompt
  exceeds the model's context window, the provider silently truncates (or
  errors). The current token estimate is `current_query.len() / 3` — telemetry
  only, not accurate enough to gate on.
- **"Lost in the middle":** even within the window, a very large prompt degrades
  the model's attention to mid-context content. Full recall in *storage* does not
  guarantee full recall in *reasoning*.

### 2.1 Proposal — compact the **context**, never the **storage**

Core invariant:

> **Lossless storage, lossy context.** Compaction only ever shrinks the prompt
> we send to the LLM for *this turn*. The SQL checkpoint and the Memvid capsule
> always remain complete. This preserves recall fidelity, audit, and erasure
> guarantees untouched.

```
✅ correct:  prompt sent to LLM  = compacted (may be lossy)
             swarm_checkpoints   = full (source of truth)
             .mv2 capsule        = full (source of truth)

❌ wrong:    summarise then overwrite history in SQL / Memvid
             → destroys fidelity + audit + erasure story
```

### 2.2 Trigger policy

- **Threshold: ~75% of the model's real context window**, not 50%. A 50% trigger
  fires far too often — most sessions never reach a problematic length, and a
  per-turn summariser call can cost *more* than simply sending a slightly larger
  prompt.
- **Hysteresis:** when usage crosses 75%, compact down to ~40%, then let it grow
  again. Avoids thrash (compact → just-over → compact …) on every turn.
- **Prerequisite:** replace `len()/3` with a real per-model token counter. The
  threshold is meaningless without accurate accounting. Token budget should be
  resolved from the model served via Heimdall.

### 2.3 What to compact — prefer retrieval over summarisation

We already have `MemvidManager::search_memory()`. Retrieving the *relevant* old
turns is lossless-ish and reuses existing infra; abstractive summarisation adds
an LLM call and is lossy. Recommended **hybrid** assembly when over threshold:

1. **PIN (never drop):** safety-critical fields — known allergies, current
   medications, `patient_id` / `tenant_id`, active problem/diagnosis. A summary
   that silently drops "penicillin allergy, mentioned 12 turns ago" is a patient
   safety hazard — this is the primary reason retrieval > summarisation here.
2. **KEEP verbatim:** the last *N* turns (recency window).
3. **MIDDLE (older turns):** replace with top-k retrieval from the Memvid
   capsule for the current query. *If* summarisation is used, restrict it to this
   band only.
4. **Run compaction with a LOCAL model** via Heimdall (e.g. gemma-local). Local
   MLX inference is free, so compaction never consumes the cloud budget even when
   the primary agent runs on a paid model.

### 2.4 Suggested shape (illustrative)

```rust
// in overseer.rs, before building augmented_query
let budget = token_budget_for(model);          // real counter, not len()/3
if estimated_tokens(&history) > budget.high_watermark() {   // ~75%
    let pinned   = extract_safety_fields(&history);          // step 1
    let recent   = history.tail(N_RECENT_TURNS);             // step 2
    let relevant = memvid.search_memory(agent_id, session_id, query, k)?; // step 3
    history_for_prompt = assemble(pinned, relevant, recent); // compact to ~40%
}
// swarm_checkpoints + .mv2 are still written in FULL on commit
```

---

## 3. Problem B — PDPA right-to-erasure on immutable Memvid (carryover)

`commit_memory()` appends **immutable, append-only** frames and there is no
prune/compaction or delete path. This collides with compliance:

- **PDPA right-to-erasure:** if a patient requests deletion, or a wrong /
  hallucinated fact was committed, we currently cannot remove or redact an
  individual frame.
- **Unbounded growth:** `.mv2` files grow forever; storage and search-index size
  per agent only increase.
- The "never forgets" property is an *auditability* asset but a *compliance*
  liability at the same time.

### 3.1 What memvid-core already gives us (verified against v2.0.139 source)

The open question "does the format support tombstones / hard redaction /
compaction?" is now **answered: YES, natively.** Confirmed by reading
`memvid-core-2.0.139` source — no fallback capsule-rebuild needed.

| Capability | API (verified) | Notes |
|------------|----------------|-------|
| **Soft delete** | `Memvid::delete_frame(frame_id) -> Result<u64>` | Appends a `FrameWalOp::Tombstone` WAL entry; frame → `FrameStatus::Deleted` on `commit()`. |
| **Physical purge** | `Memvid::vacuum() -> Result<()>` | Rebuilds the capsule keeping only `FrameStatus::Active`; drops deleted/superseded payloads + rebuilds all indexes. **Must be called** — tombstone alone leaves payload on disk until vacuum. |
| **Redact-in-place** | `Memvid::update_frame(frame_id, payload, options)` | Writes a new frame, old → `Superseded` (chained via `supersedes`/`superseded_by`). Use to rewrite a redacted payload. |
| **Versioning / time-travel** | `as_of_frame` / `as_of_ts` on `SearchRequest` | Monotonic frame IDs + supersession chain; old versions retained until `vacuum()`. |
| **Iteration** | `frame_count()` + `frame_by_id(i)` + `frame_canonical_payload(id)` | Frame IDs are dense `0..frame_count`, so full enumeration is trivial (for subject-scan deletion). |
| **ACL** | `AclEnforcementMode { Audit, Enforce }`, `AclContext { tenant_id, subject_id, roles, group_ids }` | Currently `Audit` (evaluate, don't block). Metadata-key based: `ACL_TENANT_ID_KEY`, `ACL_RESOURCE_ID_KEY`, `ACL_VISIBILITY_KEY`, … |

**Important correction:** `PutOptions` has **no `scope` field**. To tag a frame
with a subject we must use `PutOptions` → `uri` / `tags` / `labels` /
`extra_metadata` (BTreeMap). The ACL metadata-key conventions
(`ACL_TENANT_ID_KEY`, `ACL_RESOURCE_ID_KEY`) live in `extra_metadata`. `scope` is
a **search-time** filter on `SearchRequest`, not a put-time attribute.

**Granularity caveat:** `delete_frame()` is **all-or-nothing per frame** — there
is no per-tenant/per-field selective deletion. In our design each frame = one
conversation turn belonging to exactly one `{tenant, patient, session}`, so
subject-level erasure maps cleanly to "delete all frames whose
`extra_metadata.patient_id` matches". Field-level redaction inside a frame (e.g.
strip one PHI token, keep the rest) requires `update_frame()` with a rewritten
payload.

**Non-options (do not rely on these for erasure):**

- `pii.rs` (`mask_pii`, `contains_pii`) masks **at query time only** — the
  original PII stays on disk. Not erasure.
- Encryption (`lock_file`/`unlock_file`, AES-256-GCM + Argon2id) is **whole-file,
  password-based** — no per-frame key material, so **crypto-shredding is not
  available** as a selective-erasure technique.

### 3.2 Proposed erasure design (revised — uses native APIs)

1. **Tag every frame at commit time.** Extend `MemvidManager::commit_memory()` to
   accept subject identity and write `PutOptions.extra_metadata` with
   `ACL_TENANT_ID_KEY = tenant`, `patient_id = <id>` (+ optionally
   `ACL_RESOURCE_ID_KEY`). Today frames are keyed only by `agent_id` +
   `session_id` in the filename — insufficient for subject-level erasure across
   sessions.
2. **Add an erasure API to `MemvidManager`** wrapping the native calls:
   - `erase_subject(patient_id)` → enumerate (`frame_count` + `frame_by_id`),
     `delete_frame()` every frame whose `extra_metadata.patient_id` matches,
     then `vacuum()` + `commit()`.
   - `redact_frame(frame_id, new_payload)` → `update_frame()` for field-level
     redaction of a wrong/hallucinated fact.
   - **`vacuum()` is mandatory** to physically purge — a tombstone left
     un-vacuumed still has its payload on disk.
3. **Cross-capsule reach:** a subject can span many capsules (one per
   agent+session). `erase_subject` must iterate every capsule under `base_path`
   matching the tenant, not just one file. (See open question on subject-keyed
   layout.)
4. **Mirror erasure on the SQL layer:** delete/redact matching entries in
   `swarm_checkpoints.state_json` (the patient-scoped session key already exists).
5. **Tighten `AclEnforcementMode`** from `Audit` → `Enforce` for cross-tenant /
   cross-patient reads, so the ACL is not advisory-only.
6. **Audit the erasure itself** → emit an event to Tyr (erasure is a privileged,
   logged action). PII/medical erasure flows should treat Tyr as a first-class
   detection/audit layer, not an afterthought. Log frame IDs/URIs *before*
   `delete_frame()` as proof-of-erasure.

---

## 4. Sequencing & priority

1. **(Compliance blocker) Memvid erasure + per-frame `patient_id` tagging** —
   should land before any production clinical deployment. Not an optimisation.
   *Unblocked:* native `delete_frame()`/`vacuum()`/`update_frame()` exist (§3.1);
   work is wiring tagging at commit + an `erase_subject` wrapper, not new format
   support.
2. **Real per-model token counter** — prerequisite for everything in §2.
3. **Context compaction (retrieve-first hybrid, 75% + hysteresis, local model)**
   — once the counter exists.
4. **Tighten Memvid ACL enforcement** beyond `Audit`.

---

## 5. Open questions

- ~~Does memvid-core support frame tombstones / hard redaction / compaction?~~
  **RESOLVED (2026-05-22):** yes — `delete_frame()` + `vacuum()` + `update_frame()`
  in v2.0.139. See §3.1. No capsule-rebuild fallback needed.
- Per-turn redundancy: a Memvid hit can return content already present verbatim
  in the SQL history → dedupe before injecting into `manual_context`?
- Recency window size `N` and the high/low watermarks (75% / 40%) — tune against
  real session-length distribution before committing constants.
- Do we ever need cross-session subject memory (one patient, many sessions)? If
  yes, the per-`session_id` capsule filename needs rethinking (subject-keyed
  capsule or a scope-based query layer).