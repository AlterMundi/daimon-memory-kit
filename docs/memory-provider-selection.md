# Memory provider selection — 2026-10-07

The human requested an open provider comparison before resuming the paused
narrative/consolidation goal. Quality and reliable operation take priority over
keeping an inadequate setup merely because it is already configured. This is
source-based selection research, not a completed provider benchmark, account
qualification, purchase, deployment or resumption of that goal.

## Separate the jobs

There is no requirement that embeddings, selection/consolidation, narration and
verification share a provider or model. Embeddings find candidate memories;
rerankers order those candidates; a text model decides what to retain or narrates
supplied evidence. Changing a narrator cannot repair missing evidence, and a
better vector search cannot make an unsupported narrative true.

Keep source records, revisions, selected assets and vectors locally in DMK's
files/SQLite. Hosted inference does not require adopting a hosted memory store.
Provider/model choices are replaceable processing dependencies, not the being's
identity or the durable authority of its history.

Inspection of [memoryctl](../scripts/memoryctl.py) shows existing embedding
backends for NVIDIA, Google, local SentenceTransformers and Model2Vec; retrieval
selects a provider/model embedding set. The reviewed configuration currently
uses `nvidia/nemotron-3-embed-1b` with reranking disabled. Generation in the pilot
has been NVIDIA-specific. OpenAI, Qwen, Voyage and Cohere embedding endpoints,
and non-NVIDIA generation, need explicit adapters rather than only a renamed
model. Existing provider A/B tooling can be reused; compatibility is not quality.

## Text-model candidates

All prices below were inspected in primary documentation on this date, in USD
per million ordinary input/output tokens, before cache discounts. Different
tokenizers, reasoning output, retries and region/tier rules affect actual cost.
These are candidates, not claims that any model passes our recall contract.

| Candidate | Role worth testing | Published input / output price | Primary source |
|---|---|---|---|
| DeepSeek V4.1 Flash, API `deepseek-flash` | Narration and extraction; compare low reasoning with the task's necessary reasoning | $0.15–0.30 / $0.60–1.20, off-peak/peak | [Models and pricing](https://api-docs.deepseek.com/quick_start/pricing/) |
| DeepSeek V4 Pro, API `deepseek-v4-pro` | More demanding consolidation or narrative/review candidate | $0.66–1.32 / $1.98–3.96 | [Same primary pricing table](https://api-docs.deepseek.com/quick_start/pricing/) |
| Qwen 3.8 Max, API `qwen3.8-max` | Primary narration/consolidation candidate; supports structured output | $2 / $6 in Singapore; other regions differ | [Model information](https://www.alibabacloud.com/help/en/model-studio/qwen3-8-max) |
| OpenAI GPT-6 Luna | Focused narration/extraction candidate at low or medium reasoning; measure omissions and attribution errors | $0.10 / $0.50 | [Official model page](https://developers.openai.com/api/docs/models/gpt-6-luna) |
| OpenAI GPT-6.1 Sol | Moderate-effort comparison/reference where a smaller model fails; no automatic xhigh default | $2 / $10 | [Official model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol) |
| Gemini 3.6 Flash | Narration/extraction and independent-review comparison | Verify the selected API tier and current [pricing](https://ai.google.dev/gemini-api/docs/pricing) | [Exact model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash) |
| Gemini 3.1 Pro Preview | More demanding independent review/reference; preview lifecycle needs checking | Verify selected API tier/current pricing | [Exact model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview) |
| Claude Sonnet 5.5 | Independent review and narration/consolidation comparison | $2 / $10 | [Model information](https://platform.claude.com/docs/en/models/sonnet-5-5/overview) |
| Nous Portal | An existing access route to compare with direct vendors, not a single model | Qualify the actual model, route and account price | [Current model catalog](https://portal.nousresearch.com/models) |

DeepSeek's current pricing page maps the retired V4 Flash names to V4.1 Flash;
record both requested and returned versions instead of treating an old alias as
a pin. Qwen's regional capabilities and prices differ. Google's exact Pro page
labels that candidate a preview. Nous lists text and embedding catalogs; an
account/catalog entry is not proof that a selected request or region is usable.
Do not assume a paid chat subscription supplies programmatic API credits.

Using a different model family for review is a hypothesis for reducing shared
errors, not independent corroboration or a replacement for outside grading.
Do not pay for an ever-larger judge while leaving input/provenance mistakes
unexamined. The [actual Ultra diagnostic](../research/agent-memory-2026-10-06/pilots/2026-10-07-receiving-api-diagnostic.md)
already separates provider-format failures, unavailable review and narrative
errors; larger parameter counts did not qualify that run.

## Embedding and reranking candidates

| Candidate | Why inspect it | Published price / access boundary | Primary source |
|---|---|---|---|
| Voyage `voyage-4-large` with `rerank-3` | Specialist retrieval baseline, including reranking independently of narrator | Embeddings $0.12/M tokens; reranking $0.05/M processed tokens | [Pricing](https://docs.voyageai.com/docs/pricing), [reranker release](https://blog.voyageai.com/2026/09/30/rerank-3/) |
| Qwen `qwen3.7-text-embedding` with `qwen3-rerank` | Current hosted multilingual embedding candidate, with query instructions and a separate reranker | Singapore embeddings $0.07/M tokens; qualify the selected reranker endpoint/region | [Embedding API](https://www.alibabacloud.com/help/en/model-studio/embedding), [rerank API](https://www.alibabacloud.com/help/en/model-studio/text-rerank-api) |
| OpenAI `text-embedding-3-large` | Explicit multilingual/text baseline, easy to separate from any narrator | $0.13/M tokens | [Official model page](https://developers.openai.com/api/docs/models/text-embedding-3-large) |
| Gemini `gemini-embedding-2` | Current text/multimodal candidate; future selected media may benefit | Text $0.20/M tokens; other modalities have separate rates | [Model](https://ai.google.dev/gemini-api/docs/models/gemini-embedding-2), [pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Cohere `embed-v5.0-pro` / `embed-v5.0-fast`, plus `rerank-v4.0-pro` | Current specialist alternatives; compare quality and latency | Verify self-serve API pricing; Model Vault dedicated-instance prices are a different product | [Models](https://docs.cohere.com/docs/models), [release/availability](https://docs.cohere.com/v2/changelog), [pricing](https://cohere.com/pricing) |
| Existing NVIDIA model and a local multilingual model | Preserve a measured reference and assess independence from network inference | Measure actual latency, resources and provider billing | [Existing DMK backend](../scripts/memoryctl.py) |

Vendor benchmark gains justify a trial, not a claim of better lifelong recall.
Our tests need Spanish/English and cross-language weak cues, known aliases,
dated outcomes, distinct same-project episodes and recent distractions. Do not
optimize only English topical similarity or the current small fixture's IDs.

Generally, document and query vectors must come from the same compatible model,
dimensions and input conventions. Identical dimensions do not make different
models compatible. Preserve the old index and build a verified parallel index
before switching; do not mix vectors or delete source history.

There are specific compatibility claims to test rather than generalize:
Voyage advertises a shared space within its Voyage 4 family
([announcement](https://blog.voyageai.com/2026/01/15/new-models-and-expanded-availability/)).
Google explicitly says Embedding 001 and Embedding 2 spaces are incompatible;
Embedding 2 also drops the old task-type parameter and changes aggregation
([migration guidance](https://ai.google.dev/gemini-api/docs/embeddings)). The current
DMK Google adapter still sends taskType, so Embedding 2 is not a demonstrated
drop-in model-name change. Preserve query/document separation and test batches
before using any new endpoint.

## Provisional configuration and decision procedure

Current human selection: use direct DeepSeek Flash for DMK narration and as the
next consolidation candidate, retaining the existing embeddings/retrieval space.
This is provisional adoption of the working candidate, not a passed narrative
or consolidation qualification. Complete the fictional contract and distinguish
first-generation fidelity from reviewer/revision cost and full-pipeline behavior.
Gemini/Qwen and further provider expansion are deferred. The later requested
[Sol comparison](../research/agent-memory-2026-10-06/pilots/2026-10-07-flash-native-codex-comparison.md)
uses OpenAI Codex directly, not Nous, over all 44 identical frozen packets.
Both initial-answer configurations retain factual/coverage defects and have no
matched qualified reviewed workflow. Previous Nous observations retain their
actual route rather than transferring quality/price claims to Codex.

The first configuration to **test**, not deploy as a claimed winner, is:

- Hybrid lexical/vector retrieval, comparing Voyage 4 Large with Qwen 3.7 text
  embeddings and the existing model; include OpenAI/Cohere/Google as measured
  alternatives instead of silently narrowing the provider set.
- Dedicated reranking where it demonstrably improves weak-cue retrieval without
  removing distinct episodes; Voyage Rerank 3 and Qwen/Cohere are candidates.
- Qwen 3.8 Max and DeepSeek's current Flash/Pro as initial narration/consolidation
  candidates, alongside Gemini Flash and OpenAI Luna. Start with bounded reasoning
  and increase it only for a measured failure that benefits from the increase.
- Claude Sonnet or Gemini Pro as independent-family review candidates. Use
  stronger OpenAI settings only where measured fidelity warrants them.

Run small capability checks to establish endpoint availability, JSON behavior,
final-output limits and actual usage. Then use the same frozen evidence to isolate
narration/review changes. Narrow the candidates by measured fidelity and service
behavior before a complete comparison. Preserve every failure; do not select
only easy questions or pass a model on quotation copying.

For embeddings/reranking changes, create a separate retrieval experiment over
preserved source formation. Tune thresholds only on development cases, with the
same tuning budget per candidate; freeze them before hidden held-out evaluation.
The numeric cosine threshold is not inherently calibrated across model families.
Measure evidence coverage, supported answers, false attribution, source/report
time fidelity, partial/empty answers, outages, latency distribution and actual
usage/cost separately. A different retrieval packet is not an isolated narrator
comparison. Qualify the final end-to-end configuration as well.

Model review remains fallible. A supported verdict cannot discharge outside
claim-by-claim and requirement grading. Count all repairs/retries and unknown
usage; a nominally inexpensive model with many failed calls may cost more and
take longer than a stronger model that finishes correctly.

Access qualification remains pending for the new vendors. Inspect the selected
accounts' actual API configuration and region without copying credentials to
public artifacts or interpreting subscription names as API access. This review
made no inference call to a new provider, changed no live configuration/index and
contracted no service. The paused goal's next revision should name DeepSeek and
keep the provider set open. After selection, the original full narrative gate,
three consolidation passes, replay, dependent correction/reconciliation,
publication/adoption and preservation requirements remain unchanged.

Subsequent separately authorized testing reused the existing DeepSeek connection
and confirmed the Hermes compression configuration reported by the human. The
[eight-generation Flash-low diagnostic](../research/agent-memory-2026-10-06/pilots/2026-10-07-deepseek-generation-diagnostic.md)
establishes working direct inference with unchanged embeddings, not consolidation
or full narrative qualification. Three unsupported clauses and a missing source
date remain. Prefer this inexpensive candidate for the next consolidation trial;
keep Sol low as an unexecuted comparison and qualify the reviewer separately.
The broader goal remains paused; no production model or index was changed.

Later human steering selects **DeepSeek Flash for now** and defers Gemini/Qwen
comparisons. Treat that as an explicit processing choice, not a measured victory
over unevaluated vendors. Use the existing NVIDIA embedding model/index unchanged
for the isolated narrator comparison. Narrator and reviewer remain independently
configurable and frozen, even when both currently select Flash. Qualify the
complete narrative contract and then the new end-to-end formation/consolidation
configuration; retain the earlier limited diagnostics and every failure.

Read-only access inspection found an existing Nous inference credential and a
working model catalog listing OpenAI Sol/Luna, Qwen 3.8 Max, Gemini Flash and
Voyage embeddings. Catalog access is not successful inference or a qualified
component. No inference was dispatched to those candidates; they remain later
options if needed. The selected DeepSeek task continues without waiting for
additional account setup.
The human also retains Sol 6.1 low as a valid bounded comparator where consumption
is modest. A catalog route can be tested through the existing authorized Nous
API; its returned model, usage and actual routing must be recorded separately
from a direct OpenAI endpoint or a native Codex subscription.
The subsequent [actual eight-answer Sol-low comparison](../research/agent-memory-2026-10-06/pilots/2026-10-07-flash-sol-comparison.md)
uses identical Flash messages/schema. Sol is faster and concise but drops the
proposal's interest and invents Mara's gender in two clauses; its generation bill
is modest but neither full fidelity nor total reviewed-workflow cost is qualified.
Keep it as a candidate without reversing the selected Flash task prematurely.
