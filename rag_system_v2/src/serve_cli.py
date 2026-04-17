"""
serve_cli.py - Main CLI Orchestrator + Streaming Server
========================================================
Purpose: Interactive CLI that orchestrates the full RAG pipeline.
         Query → Retrieve → Rerank → Route → Prompt → Verify → Stream

Inputs:
  - User queries via interactive prompt
  - Pre-built indexes (BM25 + Qdrant)
  - LM Studio connection

Outputs:
  - Streaming responses with citations
  - JSONL trace logs per query
  - Debug mode for full pipeline visibility

Failure Modes:
  - Index not found → Clear error with rebuild instructions
  - LM Studio offline → Connection error with retry option
  - Verification failure → Regenerate or refuse (fail-closed)
  - All errors → Logged with full context

Usage:
  python -m src.serve_cli [--debug] [--no-stream]
"""

import sys
import json
import time
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict

from .config import get_config, RouterDecision, ModelTier
from .retrieve import Retriever, RetrievalResult, RetrievedChunk
from .rerank import ConditionalReranker
from .router import Router, RouterOutput
from .prompting import LLMInterface, PromptResult, StreamChunk
from .verify import CitationVerifier, VerificationResult, FixAction

logger = logging.getLogger(__name__)


# ==============================================================================
# QUERY TRACE - OBSERVABILITY
# ==============================================================================

@dataclass
class QueryTrace:
    """Complete trace of a query through the pipeline."""
    # Identity
    trace_id: str
    timestamp: str
    query: str
    
    # Retrieval
    retrieval_latency_ms: float = 0.0
    vector_candidates: int = 0
    bm25_candidates: int = 0
    merged_candidates: int = 0
    top_scores: List[float] = None
    
    # Rerank
    rerank_performed: bool = False
    rerank_latency_ms: float = 0.0
    rerank_reason: str = ""
    
    # Router
    router_decision: str = ""
    router_confidence: float = 0.0
    router_reason_codes: List[str] = None
    model_tier: str = ""
    
    # Generation
    generation_latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    prompt_hash: str = ""
    
    # Verification
    verification_status: str = ""
    verification_issues: int = 0
    verification_action: str = ""
    regeneration_count: int = 0
    
    # Final
    total_latency_ms: float = 0.0
    success: bool = False
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.top_scores is None:
            self.top_scores = []
        if self.router_reason_codes is None:
            self.router_reason_codes = []


class TraceLogger:
    """Logs query traces to JSONL file."""
    
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        
    def log(self, trace: QueryTrace):
        """Append trace to JSONL file."""
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(asdict(trace), default=str) + '\n')


# ==============================================================================
# MAIN ORCHESTRATOR
# ==============================================================================

class RAGOrchestrator:
    """
    Main RAG pipeline orchestrator.
    
    Handles the full query flow:
    1. Retrieve candidates (vector + BM25 + RRF)
    2. Conditional rerank
    3. Route (decide action)
    4. Generate response (with appropriate prompt)
    5. Verify citations
    6. Stream to user
    """
    
    MAX_REGENERATION_ATTEMPTS = 2
    
    def __init__(self, debug: bool = False):
        self.config = get_config()
        self.debug = debug
        
        # Initialize components (lazy load on first query)
        self._retriever: Optional[Retriever] = None
        self._reranker: Optional[ConditionalReranker] = None
        self._router: Optional[Router] = None
        self._llm: Optional[LLMInterface] = None
        self._verifier: Optional[CitationVerifier] = None
        
        # Trace logging
        self.trace_logger = TraceLogger(
            self.config.paths.logs_dir / "query_trace.jsonl"
        )
        
    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            logger.info("Loading retriever...")
            self._retriever = Retriever()
        return self._retriever
    
    @property
    def reranker(self) -> ConditionalReranker:
        if self._reranker is None:
            logger.info("Loading reranker...")
            self._reranker = ConditionalReranker()
        return self._reranker
    
    @property
    def router(self) -> Router:
        if self._router is None:
            self._router = Router()
        return self._router
    
    @property
    def llm(self) -> LLMInterface:
        if self._llm is None:
            logger.info("Connecting to LM Studio...")
            self._llm = LLMInterface()
        return self._llm
    
    @property
    def verifier(self) -> CitationVerifier:
        if self._verifier is None:
            self._verifier = CitationVerifier()
        return self._verifier
    
    def _generate_trace_id(self, query: str) -> str:
        """Generate unique trace ID."""
        timestamp = datetime.now().isoformat()
        hash_input = f"{timestamp}:{query}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:12]
    
    def process_query(
        self,
        query: str,
        stream: bool = True
    ) -> str:
        """
        Process a single query through the full pipeline.
        
        Args:
            query: User's query string
            stream: If True, print tokens as they arrive
            
        Returns:
            Final response string
        """
        start_time = time.perf_counter()
        trace = QueryTrace(
            trace_id=self._generate_trace_id(query),
            timestamp=datetime.now().isoformat(),
            query=query
        )
        
        try:
            # ==== STEP 1: RETRIEVE ====
            if self.debug:
                print("\n[DEBUG] Step 1: Retrieving...")
                
            retrieval_start = time.perf_counter()
            retrieval_result = self.retriever.retrieve(query)
            trace.retrieval_latency_ms = (time.perf_counter() - retrieval_start) * 1000
            
            trace.vector_candidates = retrieval_result.vector_candidates
            trace.bm25_candidates = retrieval_result.bm25_candidates
            trace.merged_candidates = len(retrieval_result.chunks)
            trace.top_scores = [c.rrf_score for c in retrieval_result.chunks[:5]]
            
            if self.debug:
                print(f"    Retrieved {len(retrieval_result.chunks)} candidates")
                print(f"    Top score: {trace.top_scores[0] if trace.top_scores else 'N/A'}")
            
            # ==== STEP 2: CONDITIONAL RERANK ====
            if self.debug:
                print("\n[DEBUG] Step 2: Conditional rerank...")
                
            chunk_tuples: List[Tuple[str, str, float]] = [
                (c.chunk_id, c.text, c.rrf_score) for c in retrieval_result.chunks
            ]
            by_chunk_id = {c.chunk_id: c for c in retrieval_result.chunks}
            
            rerank_start = time.perf_counter()
            rerank_results, was_reranked, rerank_reason = self.reranker.maybe_rerank(
                query=query,
                chunks=chunk_tuples,
                retrieval_result=retrieval_result
            )
            trace.rerank_latency_ms = (time.perf_counter() - rerank_start) * 1000
            trace.rerank_performed = was_reranked
            trace.rerank_reason = rerank_reason
            
            if self.debug:
                print(f"    Reranked: {was_reranked} ({rerank_reason})")
            
            # ==== STEP 3: ROUTE ====
            if self.debug:
                print("\n[DEBUG] Step 3: Routing...")
                
            router_output = self.router.route(
                query=query,
                retrieval_result=retrieval_result,
                rerank_results=rerank_results
            )
            
            trace.router_decision = router_output.decision.value
            trace.router_confidence = router_output.confidence
            trace.router_reason_codes = router_output.reason_codes
            trace.model_tier = router_output.model_tier.value
            
            if self.debug:
                print(f"    Decision: {router_output.decision.value}")
                print(f"    Confidence: {router_output.confidence:.3f}")
                print(f"    Reasons: {router_output.reason_codes}")
            
            # ==== STEP 4: GENERATE ====
            if self.debug:
                print("\n[DEBUG] Step 4: Generating response...")
            
            # Map rerank order back to RetrievedChunk for LLM / verifier
            chunks_for_gen: List[RetrievedChunk] = []
            for rr in rerank_results:
                src = by_chunk_id.get(rr.chunk_id)
                if src is not None:
                    chunks_for_gen.append(src)
            if not chunks_for_gen:
                chunks_for_gen = list(retrieval_result.chunks)
            chunks_for_gen = chunks_for_gen[: self.config.retrieval.final_top_k]
            
            # Get reason string
            reason_str = router_output.clarify_prompt or router_output.refuse_reason or ""
            
            gen_start = time.perf_counter()
            
            if stream and router_output.decision in (
                RouterDecision.RETRIEVE_AND_ANSWER,
                RouterDecision.NO_RETRIEVAL
            ):
                # Stream response
                response_parts = []
                print()  # Newline before streaming
                
                for chunk in self.llm.generate_stream(
                    query=query,
                    decision=router_output.decision,
                    chunks=chunks_for_gen,
                    reason=reason_str,
                    tier=router_output.model_tier
                ):
                    print(chunk.delta, end='', flush=True)
                    response_parts.append(chunk.delta)
                
                print()  # Newline after streaming
                response = ''.join(response_parts)
                
                # Approximate token counts for streaming
                trace.prompt_tokens = 0  # Not available in streaming
                trace.completion_tokens = len(response.split()) * 1.3  # Rough estimate
                
            else:
                # Non-streaming or clarify/refuse
                result, messages = self.llm.generate_response(
                    query=query,
                    decision=router_output.decision,
                    chunks=chunks_for_gen,
                    reason=reason_str,
                    tier=router_output.model_tier
                )
                response = result.content
                trace.prompt_tokens = result.prompt_tokens
                trace.completion_tokens = result.completion_tokens
                trace.prompt_hash = result.prompt_hash
                
                print(f"\n{response}")
            
            trace.generation_latency_ms = (time.perf_counter() - gen_start) * 1000
            
            # ==== STEP 5: VERIFY (only for grounded answers) ====
            if router_output.decision == RouterDecision.RETRIEVE_AND_ANSWER:
                if self.debug:
                    print("\n[DEBUG] Step 5: Verifying citations...")
                
                verification = self.verifier.verify(
                    response=response,
                    chunks=chunks_for_gen,
                    query=query
                )
                
                trace.verification_status = verification.status.value
                trace.verification_issues = len(verification.issues)
                trace.verification_action = verification.fix_action.value
                
                if self.debug:
                    print(f"    Status: {verification.status.value}")
                    print(f"    Issues: {len(verification.issues)}")
                
                # Handle verification failure
                if verification.fix_action == FixAction.REGENERATE:
                    for attempt in range(self.MAX_REGENERATION_ATTEMPTS):
                        trace.regeneration_count += 1
                        if self.debug:
                            print(f"\n[DEBUG] Regenerating (attempt {attempt + 1})...")
                        
                        # Regenerate with stricter prompt
                        result, _ = self.llm.generate_response(
                            query=query,
                            decision=router_output.decision,
                            chunks=chunks_for_gen,
                            reason="Be very careful to cite every claim.",
                            tier=router_output.model_tier
                        )
                        response = result.content
                        
                        # Re-verify
                        verification = self.verifier.verify(
                            response=response,
                            chunks=chunks_for_gen,
                            query=query,
                            strict=True
                        )
                        
                        if verification.is_acceptable():
                            print(f"\n[Regenerated]\n{response}")
                            break
                    else:
                        # All attempts failed, refuse
                        response = (
                            "I found relevant information but couldn't generate a "
                            "properly cited response. Please try rephrasing your question "
                            "or ask about a more specific topic."
                        )
                        print(f"\n{response}")
                
                elif verification.fix_action == FixAction.REFUSE:
                    response = (
                        "I found some information but cannot provide a reliable answer. "
                        "The available sources may be incomplete or conflicting."
                    )
                    print(f"\n{response}")
            else:
                trace.verification_status = "skipped"
                trace.verification_action = "none"
            
            trace.success = True
            
        except ConnectionError as e:
            trace.error = str(e)
            trace.success = False
            response = f"Error: Cannot connect to LM Studio. {e}"
            print(f"\n{response}")
            
        except FileNotFoundError as e:
            trace.error = str(e)
            trace.success = False
            response = f"Error: Index files not found. Run: python -m src.index_qdrant && python -m src.index_bm25"
            print(f"\n{response}")
            
        except Exception as e:
            logger.exception("Query processing failed")
            trace.error = str(e)
            trace.success = False
            response = f"Error: {e}"
            print(f"\n{response}")
        
        finally:
            trace.total_latency_ms = (time.perf_counter() - start_time) * 1000
            self.trace_logger.log(trace)
            
            if self.debug:
                print(f"\n[DEBUG] Total latency: {trace.total_latency_ms:.0f}ms")
        
        return response


# ==============================================================================
# INTERACTIVE CLI
# ==============================================================================

def print_banner():
    """Print startup banner."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║           RAG System v2 - Hardened Local Pipeline            ║
║                                                              ║
║  Commands:                                                   ║
║    /debug    - Toggle debug mode                             ║
║    /stream   - Toggle streaming                              ║
║    /stats    - Show session stats                            ║
║    /quit     - Exit                                          ║
╚══════════════════════════════════════════════════════════════╝
""")


def run_interactive():
    """Run interactive CLI loop."""
    import argparse
    
    parser = argparse.ArgumentParser(description="RAG System v2 CLI")
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--no-stream', action='store_true', help='Disable streaming')
    args = parser.parse_args()
    
    print_banner()
    
    orchestrator = RAGOrchestrator(debug=args.debug)
    stream_enabled = not args.no_stream
    
    # Session stats
    query_count = 0
    total_latency = 0.0
    
    print("Loading components (this may take a moment on first query)...\n")
    
    # Piped stdin (Gate 2 automation): avoid a second `input()` blocking forever while the
    # parent waits on stdout (PowerShell + Tee). Use readline + EOF instead of console `input()`.
    stdin_is_tty = sys.stdin.isatty()
    
    while True:
        try:
            if stdin_is_tty:
                try:
                    query = input("You: ").strip()
                except EOFError:
                    print("\nGoodbye!")
                    break
            else:
                raw = sys.stdin.readline()
                if raw == "":
                    break
                query = raw.strip()
            
            if not query:
                continue
                
            # Handle commands
            if query.startswith('/'):
                cmd = query.lower()
                
                if cmd == '/quit' or cmd == '/exit':
                    print("Goodbye!")
                    break
                    
                elif cmd == '/debug':
                    orchestrator.debug = not orchestrator.debug
                    print(f"Debug mode: {'ON' if orchestrator.debug else 'OFF'}")
                    continue
                    
                elif cmd == '/stream':
                    stream_enabled = not stream_enabled
                    print(f"Streaming: {'ON' if stream_enabled else 'OFF'}")
                    continue
                    
                elif cmd == '/stats':
                    avg = total_latency / query_count if query_count > 0 else 0
                    print(f"Queries: {query_count}, Avg latency: {avg:.0f}ms")
                    continue
                    
                else:
                    print(f"Unknown command: {query}")
                    continue
            
            # Process query
            start = time.perf_counter()
            response = orchestrator.process_query(query, stream=stream_enabled)
            latency = (time.perf_counter() - start) * 1000
            
            query_count += 1
            total_latency += latency
            
            print(f"\n[{latency:.0f}ms]\n")
            
        except KeyboardInterrupt:
            print("\n\nInterrupted. Type /quit to exit.")
            continue


# ==============================================================================
# SINGLE QUERY MODE
# ==============================================================================

def run_single_query(query: str, debug: bool = False, stream: bool = True):
    """Process a single query and exit."""
    orchestrator = RAGOrchestrator(debug=debug)
    response = orchestrator.process_query(query, stream=stream)
    return response


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Reduce noise from libraries
    logging.getLogger('sentence_transformers').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    
    run_interactive()
