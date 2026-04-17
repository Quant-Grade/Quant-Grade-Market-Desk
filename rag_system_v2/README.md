# RAG System v2 - Hardened Local Pipeline

Production-grade local-first RAG system with:
- **High precision + high recall** via hybrid retrieval (BM25 + Vector + RRF)
- **Fail-closed router** - prefers "I don't know" over wrong answers
- **Prompt injection defense** - retrieved text treated as untrusted data
- **Citation enforcement** - every claim must cite a chunk
- **Full observability** - JSONL traces, eval harness, threshold calibration

## Requirements

- Windows 10/11
- Python 3.10+
- 16GB RAM (for embeddings + indexes)
- GPU optional (CPU works, GPU auto-detected)
- LM Studio running at `http://127.0.0.1:1234/v1`

## Paths and layout

- **Install root**: the `rag_system_v2` directory (contains `src/`, `data/`, `logs/`).
- **`RAG_V2_BASE_DIR`**: optional environment variable; if unset, defaults to that install root (resolved from `src/repo_paths.py`, not a machine-specific path).
- **Parent store file**: `data/parents.sqlite` (same path as `config.paths.parents_db_path`).

## Quickstart

### 1. Install Dependencies

From the repository root (the folder that **contains** `rag_system_v2/`):

```powershell
cd rag_system_v2
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Or set `RAG_V2_BASE_DIR` to an absolute path to this `rag_system_v2` folder if you run commands from another working directory.

### 2. Add Your Documents

Place documents in `./docs/` folder:
- Supported: PDF, MD, TXT, PY, JS, TS

```powershell
mkdir docs
# Copy your files into ./docs/
```

### 3. Ingest Documents

```powershell
python -m src.ingest --docs ./docs --output ./data/chunks.jsonl
```

Output: `./data/chunks.jsonl` with parent-child chunks

### 4. Build Indexes

```powershell
# Build Qdrant vector index
python -m src.index_qdrant --chunks ./data/chunks.jsonl

# Build BM25 lexical index
python -m src.index_bm25 --chunks ./data/chunks.jsonl
```

### 5. Start LM Studio

1. Open LM Studio
2. Load a model (7B for fast, 13B+ for smart)
3. Start server on port 1234

### 6. Run Interactive CLI

```powershell
python -m src.serve_cli
```

Commands:
- `/debug` - Toggle debug mode
- `/stream` - Toggle streaming
- `/stats` - Show session stats
- `/quit` - Exit

## Architecture

```
Query
  │
  ├──► Retrieve (Vector + BM25)
  │       └── RRF Fusion
  │
  ├──► Conditional Rerank
  │       └── Skip if both retrievers agree
  │
  ├──► Router Decision
  │       ├── NO_RETRIEVAL (chitchat)
  │       ├── RETRIEVE_AND_ANSWER (grounded)
  │       ├── ASK_CLARIFY (ambiguous)
  │       └── REFUSE_NO_EVIDENCE (can't help)
  │
  ├──► Generate (LM Studio)
  │       └── Citation-enforced prompts
  │
  └──► Verify Citations
          └── Regenerate or refuse if invalid
```

## Configuration

Edit `src/config.py` to customize:

```python
# Thresholds (MUST calibrate via eval harness)
T_RETRIEVE_CONFIDENCE = 0.50
T_EVIDENCE_COUNT_MIN = 2
T_SCORE_GAP_SUSPICIOUS = 0.30

# Models
FAST_MODEL = "qwen2.5-7b-instruct"
SMART_MODEL = "qwen2.5-14b-instruct"

# LM Studio
BASE_URL = "http://127.0.0.1:1234/v1"
```

## Evaluation Harness

### Build Test Set

```powershell
python -m src.eval build-testset --chunks ./data/chunks.jsonl --output ./tests/testset.jsonl --size 100
```

### Run Evaluation

```powershell
python -m src.eval run --testset ./tests/testset.jsonl --output ./reports --verbose
```

### Calibrate Thresholds

```powershell
python -m src.eval calibrate --testset ./tests/testset.jsonl
```

This outputs recommended threshold values based on your corpus.

## Observability

Query traces logged to `./logs/query_trace.jsonl`:

```json
{
  "trace_id": "abc123",
  "query": "What is...",
  "router_decision": "RETRIEVE_AND_ANSWER",
  "retrieval_latency_ms": 150,
  "total_latency_ms": 2500,
  "success": true
}
```

## Fail-Closed Behavior

The system fails safely:

| Condition | Action |
|-----------|--------|
| No chunks above threshold | REFUSE_NO_EVIDENCE |
| Query too short (<3 tokens) | ASK_CLARIFY |
| Prompt injection detected | REFUSE |
| Citation verification fails | Regenerate or REFUSE |
| LM Studio offline | ConnectionError (no guessing) |
| Index not found | FileNotFoundError (rebuild instructions) |

## Troubleshooting

### "Cannot connect to LM Studio"

1. Ensure LM Studio is running
2. Check server is on port 1234
3. Verify model is loaded

### "Index files not found"

Run the index build commands:
```powershell
python -m src.index_qdrant --chunks ./data/chunks.jsonl
python -m src.index_bm25 --chunks ./data/chunks.jsonl
```

### Slow first query

First query loads embeddings model (~500MB). Subsequent queries are fast.

### High latency (>3s)

1. Enable GPU if available
2. Reduce `fusion_top_k` in config
3. Enable conditional rerank skipping
4. Use smaller embedding model

### Low recall

1. Run eval harness to check metrics
2. Calibrate thresholds
3. Check chunking (parent too large? child overlap?)
4. Verify BM25 tokenizer matches query style

## Data Integrity

- **Stable chunk IDs**: Hash of doc_id + parent_idx + child_idx (survives rebuilds)
- **Deduplication**: SHA-256 at doc and chunk level
- **Atomic writes**: SQLite for parent storage
- **Corruption detection**: Qdrant + BM25 ID mapping validated

## Project Structure

```
rag_system_v2/
├── data/
│   ├── qdrant/          # Vector index
│   ├── chunks.jsonl     # Ingested chunks
│   ├── bm25_index.pkl   # BM25 index
│   └── parents.sqlite   # Parent chunk SQLite (see repo_paths.PARENTS_STORE_FILENAME)
├── logs/
│   └── query_trace.jsonl
├── reports/
│   ├── latest.json
│   └── latest.txt
├── src/
│   ├── config.py        # All configuration
│   ├── ingest.py        # Document ingestion
│   ├── index_bm25.py    # BM25 index
│   ├── index_qdrant.py  # Qdrant vector index
│   ├── merge_rrf.py     # RRF fusion
│   ├── retrieve.py      # Main retriever
│   ├── rerank.py        # Cross-encoder reranker
│   ├── router.py        # Decision router
│   ├── prompting.py     # LLM prompts
│   ├── verify.py        # Citation verification
│   ├── serve_cli.py     # Interactive CLI
│   └── eval.py          # Evaluation harness
├── tests/
│   └── testset.jsonl
├── docs/                # Your documents
├── requirements.txt
└── README.md
```

## License

Internal use only. RaveBear's trading infrastructure.
