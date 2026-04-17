"""
eval.py - Evaluation Harness
============================
Purpose: Build test sets, run evaluations, calibrate thresholds, regression testing.
         This is the CORE of ensuring system quality.

Inputs:
  - Document corpus for test set generation
  - Existing test set (JSONL)
  - Current thresholds to test

Outputs:
  - Metrics: Recall@k, MRR, nDCG, faithfulness, citation precision
  - Threshold calibration recommendations
  - Regression test results
  - HTML/JSON reports

Failure Modes:
  - Test set too small → Unreliable metrics (warn)
  - Index not built → Cannot evaluate (error)
  - LM Studio offline → Cannot test generation (partial eval)

Usage:
  # Build test set from docs
  python -m src.eval build-testset --docs ./docs --output ./tests/testset.jsonl

  # Run full evaluation
  python -m src.eval run --testset ./tests/testset.jsonl --output ./reports/

  # Calibrate thresholds
  python -m src.eval calibrate --testset ./tests/testset.jsonl

  # Regression test
  python -m src.eval regression --testset ./tests/testset.jsonl
"""

import json
import time
import logging
import random
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import statistics

from .config import get_config, RouterDecision
from .retrieve import Retriever, RetrievalResult
from .rerank import ConditionalReranker
from .router import Router

logger = logging.getLogger(__name__)


# ==============================================================================
# TEST SET DATA STRUCTURES
# ==============================================================================

@dataclass
class TestCase:
    """Single test case for evaluation."""
    id: str
    query: str
    expected_chunk_ids: List[str]  # Gold standard chunks that should be retrieved
    category: str  # "exact", "semantic", "hard_negative", "out_of_domain"
    difficulty: str  # "easy", "medium", "hard"
    expected_decision: Optional[str] = None  # Expected router decision
    notes: str = ""


@dataclass
class RetrievalMetrics:
    """Retrieval quality metrics."""
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    recall_at_20: float = 0.0
    mrr: float = 0.0  # Mean Reciprocal Rank
    ndcg_at_10: float = 0.0
    
    # Per-retriever breakdown
    vector_recall_at_10: float = 0.0
    bm25_recall_at_10: float = 0.0
    fusion_improvement: float = 0.0  # How much RRF helps


@dataclass
class RouterMetrics:
    """Router quality metrics."""
    accuracy: float = 0.0
    precision_retrieve: float = 0.0
    recall_retrieve: float = 0.0
    false_positive_rate: float = 0.0  # Said RETRIEVE when should REFUSE
    false_negative_rate: float = 0.0  # Said REFUSE when should RETRIEVE
    clarify_rate: float = 0.0  # How often does it ask for clarification


@dataclass
class LatencyMetrics:
    """Latency breakdown."""
    retrieval_p50_ms: float = 0.0
    retrieval_p95_ms: float = 0.0
    rerank_p50_ms: float = 0.0
    rerank_p95_ms: float = 0.0
    total_p50_ms: float = 0.0
    total_p95_ms: float = 0.0


@dataclass
class EvaluationReport:
    """Complete evaluation report."""
    timestamp: str
    test_set_size: int
    retrieval: RetrievalMetrics
    router: RouterMetrics
    latency: LatencyMetrics
    
    # Details
    failed_cases: List[Dict[str, Any]] = field(default_factory=list)
    threshold_recommendations: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def save_json(self, path: Path):
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def save_summary(self, path: Path):
        """Save human-readable summary."""
        with open(path, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("RAG System v2 Evaluation Report\n")
            f.write(f"Generated: {self.timestamp}\n")
            f.write(f"Test cases: {self.test_set_size}\n")
            f.write("=" * 60 + "\n\n")
            
            f.write("RETRIEVAL METRICS\n")
            f.write("-" * 40 + "\n")
            f.write(f"  Recall@5:  {self.retrieval.recall_at_5:.3f}\n")
            f.write(f"  Recall@10: {self.retrieval.recall_at_10:.3f}\n")
            f.write(f"  Recall@20: {self.retrieval.recall_at_20:.3f}\n")
            f.write(f"  MRR:       {self.retrieval.mrr:.3f}\n")
            f.write(f"  nDCG@10:   {self.retrieval.ndcg_at_10:.3f}\n")
            f.write(f"\n  Vector-only Recall@10:  {self.retrieval.vector_recall_at_10:.3f}\n")
            f.write(f"  BM25-only Recall@10:    {self.retrieval.bm25_recall_at_10:.3f}\n")
            f.write(f"  Fusion improvement:     {self.retrieval.fusion_improvement:+.3f}\n")
            
            f.write("\nROUTER METRICS\n")
            f.write("-" * 40 + "\n")
            f.write(f"  Accuracy:           {self.router.accuracy:.3f}\n")
            f.write(f"  Retrieve precision: {self.router.precision_retrieve:.3f}\n")
            f.write(f"  Retrieve recall:    {self.router.recall_retrieve:.3f}\n")
            f.write(f"  False positive:     {self.router.false_positive_rate:.3f}\n")
            f.write(f"  False negative:     {self.router.false_negative_rate:.3f}\n")
            f.write(f"  Clarify rate:       {self.router.clarify_rate:.3f}\n")
            
            f.write("\nLATENCY METRICS\n")
            f.write("-" * 40 + "\n")
            f.write(f"  Retrieval p50: {self.latency.retrieval_p50_ms:.0f}ms\n")
            f.write(f"  Retrieval p95: {self.latency.retrieval_p95_ms:.0f}ms\n")
            f.write(f"  Total p50:     {self.latency.total_p50_ms:.0f}ms\n")
            f.write(f"  Total p95:     {self.latency.total_p95_ms:.0f}ms\n")
            
            if self.threshold_recommendations:
                f.write("\nTHRESHOLD RECOMMENDATIONS\n")
                f.write("-" * 40 + "\n")
                for name, value in self.threshold_recommendations.items():
                    f.write(f"  {name}: {value:.3f}\n")
            
            if self.failed_cases:
                f.write(f"\nFAILED CASES ({len(self.failed_cases)})\n")
                f.write("-" * 40 + "\n")
                for case in self.failed_cases[:10]:
                    f.write(f"  - {case.get('id', 'unknown')}: {case.get('reason', 'unknown')}\n")


# ==============================================================================
# TEST SET BUILDER
# ==============================================================================

class TestSetBuilder:
    """
    Builds evaluation test sets from document corpus.
    
    Strategies:
    1. Extract key terms/entities from chunks → create queries
    2. Use section headers as queries
    3. Create paraphrased versions
    4. Add hard negatives (similar but wrong)
    5. Add out-of-domain queries
    """
    
    def __init__(self):
        self.config = get_config()
        
    def load_chunks(self, chunks_path: Path) -> List[Dict[str, Any]]:
        """Load chunks from JSONL."""
        chunks = []
        with open(chunks_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    chunks.append(json.loads(line))
        return chunks
    
    def extract_key_terms(self, text: str) -> List[str]:
        """Extract key terms that could form queries."""
        import re
        
        # Find capitalized phrases (potential entities)
        entities = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', text)
        
        # Find technical terms (contains numbers/special chars)
        technical = re.findall(r'\b[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9]+)+\b', text)
        
        # Find quoted terms
        quoted = re.findall(r'"([^"]+)"', text)
        
        return list(set(entities[:5] + technical[:3] + quoted[:2]))
    
    def generate_query_from_chunk(
        self, 
        chunk: Dict[str, Any],
        style: str = "direct"
    ) -> Optional[str]:
        """
        Generate a test query from a chunk.
        
        Styles:
        - direct: Use key terms directly
        - question: Form a question about the content
        - paraphrase: Rephrase the main idea
        """
        text = chunk.get('text', '')
        
        if style == "direct":
            terms = self.extract_key_terms(text)
            if terms:
                return ' '.join(terms[:3])
                
        elif style == "question":
            # Try to form a question from first sentence
            first_sentence = text.split('.')[0].strip()
            if len(first_sentence) > 20:
                # Simple transformation
                if first_sentence.lower().startswith('the '):
                    return f"What is {first_sentence[4:]}?"
                return f"What about {first_sentence[:50]}?"
                
        return None
    
    def build_test_set(
        self,
        chunks_path: Path,
        output_path: Path,
        size: int = 100,
        include_hard_negatives: bool = True,
        include_out_of_domain: bool = True
    ) -> List[TestCase]:
        """
        Build a test set from chunks.
        
        Args:
            chunks_path: Path to chunks.jsonl
            output_path: Where to save test set
            size: Target number of test cases
            include_hard_negatives: Add similar-but-wrong queries
            include_out_of_domain: Add queries with no answer in corpus
        """
        chunks = self.load_chunks(chunks_path)
        
        if not chunks:
            raise ValueError(f"No chunks found in {chunks_path}")
        
        test_cases = []
        
        # Sample chunks for query generation
        sampled = random.sample(chunks, min(len(chunks), size * 2))
        
        for chunk in sampled:
            if len(test_cases) >= size * 0.7:  # 70% normal cases
                break
                
            query = self.generate_query_from_chunk(chunk, "direct")
            if not query:
                continue
                
            case_id = hashlib.sha256(query.encode()).hexdigest()[:8]
            
            test_cases.append(TestCase(
                id=case_id,
                query=query,
                expected_chunk_ids=[chunk['chunk_id']],
                category="exact",
                difficulty="easy",
                expected_decision="RETRIEVE_AND_ANSWER"
            ))
        
        # Add question-style queries
        for chunk in sampled[len(test_cases):]:
            if len(test_cases) >= size * 0.85:
                break
                
            query = self.generate_query_from_chunk(chunk, "question")
            if not query:
                continue
                
            case_id = hashlib.sha256(query.encode()).hexdigest()[:8]
            
            test_cases.append(TestCase(
                id=case_id,
                query=query,
                expected_chunk_ids=[chunk['chunk_id']],
                category="semantic",
                difficulty="medium",
                expected_decision="RETRIEVE_AND_ANSWER"
            ))
        
        # Add out-of-domain queries
        if include_out_of_domain:
            ood_queries = [
                "What is the weather in Tokyo today?",
                "Who won the 2024 Super Bowl?",
                "How do I bake chocolate chip cookies?",
                "What is the capital of Australia?",
                "Explain quantum entanglement simply"
            ]
            
            for query in ood_queries[:max(1, int(size * 0.1))]:
                case_id = hashlib.sha256(query.encode()).hexdigest()[:8]
                test_cases.append(TestCase(
                    id=case_id,
                    query=query,
                    expected_chunk_ids=[],
                    category="out_of_domain",
                    difficulty="easy",
                    expected_decision="REFUSE_NO_EVIDENCE"
                ))
        
        # Save test set
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            for case in test_cases:
                f.write(json.dumps(asdict(case)) + '\n')
        
        logger.info(f"Built test set with {len(test_cases)} cases → {output_path}")
        return test_cases


# ==============================================================================
# EVALUATOR
# ==============================================================================

class Evaluator:
    """
    Main evaluation engine.
    
    Runs test cases through the pipeline and computes metrics.
    """
    
    def __init__(self):
        self.config = get_config()
        self._retriever: Optional[Retriever] = None
        self._reranker: Optional[ConditionalReranker] = None
        self._router: Optional[Router] = None
        
    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            self._retriever = Retriever()
        return self._retriever
    
    @property
    def reranker(self) -> ConditionalReranker:
        if self._reranker is None:
            self._reranker = ConditionalReranker()
        return self._reranker
    
    @property
    def router(self) -> Router:
        if self._router is None:
            self._router = Router()
        return self._router
    
    def load_test_set(self, path: Path) -> List[TestCase]:
        """Load test set from JSONL."""
        cases = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    cases.append(TestCase(**data))
        return cases
    
    def _compute_recall_at_k(
        self,
        retrieved_ids: List[str],
        expected_ids: List[str],
        k: int
    ) -> float:
        """Compute Recall@k."""
        if not expected_ids:
            return 1.0  # Vacuously true
            
        retrieved_set = set(retrieved_ids[:k])
        expected_set = set(expected_ids)
        
        hits = len(retrieved_set & expected_set)
        return hits / len(expected_set)
    
    def _compute_mrr(
        self,
        retrieved_ids: List[str],
        expected_ids: List[str]
    ) -> float:
        """Compute Mean Reciprocal Rank."""
        if not expected_ids:
            return 1.0
            
        expected_set = set(expected_ids)
        
        for i, rid in enumerate(retrieved_ids):
            if rid in expected_set:
                return 1.0 / (i + 1)
        
        return 0.0
    
    def _compute_ndcg_at_k(
        self,
        retrieved_ids: List[str],
        expected_ids: List[str],
        k: int
    ) -> float:
        """Compute nDCG@k."""
        import math
        
        if not expected_ids:
            return 1.0
            
        expected_set = set(expected_ids)
        
        # Compute DCG
        dcg = 0.0
        for i, rid in enumerate(retrieved_ids[:k]):
            if rid in expected_set:
                dcg += 1.0 / math.log2(i + 2)  # i+2 because log2(1)=0
        
        # Compute ideal DCG
        idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(expected_ids), k)))
        
        if idcg == 0:
            return 0.0
            
        return dcg / idcg
    
    def _percentile(self, values: List[float], p: int) -> float:
        """Compute percentile."""
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * p / 100)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]
    
    def run_evaluation(
        self,
        test_set: List[TestCase],
        verbose: bool = False
    ) -> EvaluationReport:
        """
        Run full evaluation on test set.
        """
        # Accumulators
        recall_5s, recall_10s, recall_20s = [], [], []
        mrrs, ndcgs = [], []
        vector_recalls, bm25_recalls = [], []
        
        router_correct = 0
        router_total = 0
        retrieve_tp, retrieve_fp, retrieve_fn = 0, 0, 0
        clarify_count = 0
        
        retrieval_latencies = []
        rerank_latencies = []
        total_latencies = []
        
        failed_cases = []
        
        for i, case in enumerate(test_set):
            if verbose and i % 10 == 0:
                print(f"Evaluating {i+1}/{len(test_set)}...")
            
            start_time = time.perf_counter()
            
            try:
                # Retrieve
                ret_start = time.perf_counter()
                result = self.retriever.retrieve(case.query)
                retrieval_latencies.append((time.perf_counter() - ret_start) * 1000)
                
                retrieved_ids = [c.metadata['chunk_id'] for c in result.chunks]
                
                # Compute retrieval metrics
                recall_5s.append(self._compute_recall_at_k(retrieved_ids, case.expected_chunk_ids, 5))
                recall_10s.append(self._compute_recall_at_k(retrieved_ids, case.expected_chunk_ids, 10))
                recall_20s.append(self._compute_recall_at_k(retrieved_ids, case.expected_chunk_ids, 20))
                mrrs.append(self._compute_mrr(retrieved_ids, case.expected_chunk_ids))
                ndcgs.append(self._compute_ndcg_at_k(retrieved_ids, case.expected_chunk_ids, 10))
                
                # Get per-retriever recall (from stats if available)
                vector_recall = self._compute_recall_at_k(
                    result.stats.get('vector_ids', retrieved_ids)[:10],
                    case.expected_chunk_ids, 10
                )
                bm25_recall = self._compute_recall_at_k(
                    result.stats.get('bm25_ids', retrieved_ids)[:10],
                    case.expected_chunk_ids, 10
                )
                vector_recalls.append(vector_recall)
                bm25_recalls.append(bm25_recall)
                
                # Rerank (optional)
                rerank_start = time.perf_counter()
                reranked, was_reranked, reason = self.reranker.maybe_rerank(case.query, result)
                if was_reranked:
                    rerank_latencies.append((time.perf_counter() - rerank_start) * 1000)
                
                # Route
                router_output = self.router.route(case.query, result)
                
                # Check router decision
                if case.expected_decision:
                    router_total += 1
                    actual = router_output.decision.value
                    expected = case.expected_decision
                    
                    if actual == expected:
                        router_correct += 1
                    else:
                        failed_cases.append({
                            'id': case.id,
                            'type': 'router',
                            'expected': expected,
                            'actual': actual,
                            'query': case.query[:50]
                        })
                    
                    # Precision/recall for RETRIEVE decision
                    should_retrieve = expected == "RETRIEVE_AND_ANSWER"
                    did_retrieve = actual == "RETRIEVE_AND_ANSWER"
                    
                    if should_retrieve and did_retrieve:
                        retrieve_tp += 1
                    elif not should_retrieve and did_retrieve:
                        retrieve_fp += 1
                    elif should_retrieve and not did_retrieve:
                        retrieve_fn += 1
                    
                    if actual == "ASK_CLARIFY":
                        clarify_count += 1
                
                total_latencies.append((time.perf_counter() - start_time) * 1000)
                
            except Exception as e:
                logger.warning(f"Case {case.id} failed: {e}")
                failed_cases.append({
                    'id': case.id,
                    'type': 'error',
                    'reason': str(e),
                    'query': case.query[:50]
                })
        
        # Compute final metrics
        retrieval_metrics = RetrievalMetrics(
            recall_at_5=statistics.mean(recall_5s) if recall_5s else 0,
            recall_at_10=statistics.mean(recall_10s) if recall_10s else 0,
            recall_at_20=statistics.mean(recall_20s) if recall_20s else 0,
            mrr=statistics.mean(mrrs) if mrrs else 0,
            ndcg_at_10=statistics.mean(ndcgs) if ndcgs else 0,
            vector_recall_at_10=statistics.mean(vector_recalls) if vector_recalls else 0,
            bm25_recall_at_10=statistics.mean(bm25_recalls) if bm25_recalls else 0,
            fusion_improvement=(
                statistics.mean(recall_10s) - 
                max(statistics.mean(vector_recalls) if vector_recalls else 0,
                    statistics.mean(bm25_recalls) if bm25_recalls else 0)
            ) if recall_10s else 0
        )
        
        # Router metrics
        retrieve_precision = retrieve_tp / (retrieve_tp + retrieve_fp) if (retrieve_tp + retrieve_fp) > 0 else 0
        retrieve_recall = retrieve_tp / (retrieve_tp + retrieve_fn) if (retrieve_tp + retrieve_fn) > 0 else 0
        
        router_metrics = RouterMetrics(
            accuracy=router_correct / router_total if router_total > 0 else 0,
            precision_retrieve=retrieve_precision,
            recall_retrieve=retrieve_recall,
            false_positive_rate=retrieve_fp / router_total if router_total > 0 else 0,
            false_negative_rate=retrieve_fn / router_total if router_total > 0 else 0,
            clarify_rate=clarify_count / router_total if router_total > 0 else 0
        )
        
        # Latency metrics
        latency_metrics = LatencyMetrics(
            retrieval_p50_ms=self._percentile(retrieval_latencies, 50),
            retrieval_p95_ms=self._percentile(retrieval_latencies, 95),
            rerank_p50_ms=self._percentile(rerank_latencies, 50) if rerank_latencies else 0,
            rerank_p95_ms=self._percentile(rerank_latencies, 95) if rerank_latencies else 0,
            total_p50_ms=self._percentile(total_latencies, 50),
            total_p95_ms=self._percentile(total_latencies, 95)
        )
        
        return EvaluationReport(
            timestamp=datetime.now().isoformat(),
            test_set_size=len(test_set),
            retrieval=retrieval_metrics,
            router=router_metrics,
            latency=latency_metrics,
            failed_cases=failed_cases
        )


# ==============================================================================
# THRESHOLD CALIBRATOR
# ==============================================================================

class ThresholdCalibrator:
    """
    Calibrate router thresholds from evaluation data.
    
    Analyzes score distributions to find optimal thresholds
    that maximize precision while maintaining recall.
    """
    
    def __init__(self):
        self.config = get_config()
        self._retriever: Optional[Retriever] = None
        
    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            self._retriever = Retriever()
        return self._retriever
    
    def collect_score_distributions(
        self,
        test_set: List[TestCase],
        verbose: bool = False
    ) -> Dict[str, List[Tuple[float, bool]]]:
        """
        Collect score distributions for threshold analysis.
        
        Returns dict mapping metric name to list of (score, is_positive) tuples.
        """
        distributions = defaultdict(list)
        
        for i, case in enumerate(test_set):
            if verbose and i % 20 == 0:
                print(f"Collecting {i+1}/{len(test_set)}...")
            
            try:
                result = self.retriever.retrieve(case.query)
                
                # Is this a positive case (should retrieve)?
                is_positive = case.expected_decision == "RETRIEVE_AND_ANSWER"
                
                if result.chunks:
                    # Top RRF score
                    distributions['top_rrf_score'].append(
                        (result.chunks[0].rrf_score, is_positive)
                    )
                    
                    # Score gap
                    if len(result.chunks) >= 2:
                        gap = result.chunks[0].rrf_score - result.chunks[1].rrf_score
                        distributions['score_gap'].append((gap, is_positive))
                    
                    # Evidence count (chunks above threshold)
                    evidence = sum(1 for c in result.chunks if c.rrf_score > 0.02)
                    distributions['evidence_count'].append((float(evidence), is_positive))
                
                # Quality signals
                if result.quality_signals:
                    for key, value in result.quality_signals.items():
                        if isinstance(value, (int, float)):
                            distributions[f'signal_{key}'].append((float(value), is_positive))
                            
            except Exception as e:
                logger.warning(f"Case {case.id} failed: {e}")
        
        return dict(distributions)
    
    def find_optimal_threshold(
        self,
        scores: List[Tuple[float, bool]],
        target_precision: float = 0.95
    ) -> Tuple[float, Dict[str, float]]:
        """
        Find threshold that achieves target precision.
        
        Returns (threshold, metrics_at_threshold).
        """
        if not scores:
            return 0.5, {}
        
        # Sort by score descending
        sorted_scores = sorted(scores, key=lambda x: x[0], reverse=True)
        
        best_threshold = sorted_scores[0][0]
        best_f1 = 0
        best_metrics = {}
        
        # Try each score as threshold
        for i, (score, _) in enumerate(sorted_scores):
            # Compute precision/recall at this threshold
            above_threshold = [(s, label) for s, label in scores if s >= score]
            
            if not above_threshold:
                continue
                
            tp = sum(1 for _, label in above_threshold if label)
            fp = sum(1 for _, label in above_threshold if not label)
            fn = sum(1 for s, label in scores if label and s < score)
            
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            
            # Check if this meets target precision
            if precision >= target_precision and f1 > best_f1:
                best_threshold = score
                best_f1 = f1
                best_metrics = {
                    'precision': precision,
                    'recall': recall,
                    'f1': f1,
                    'threshold': score
                }
        
        return best_threshold, best_metrics
    
    def calibrate(
        self,
        test_set: List[TestCase],
        verbose: bool = False
    ) -> Dict[str, float]:
        """
        Calibrate all thresholds from test set.
        
        Returns dict of threshold_name -> recommended_value.
        """
        print("Collecting score distributions...")
        distributions = self.collect_score_distributions(test_set, verbose)
        
        recommendations = {}
        
        # Calibrate top score threshold
        if 'top_rrf_score' in distributions:
            threshold, metrics = self.find_optimal_threshold(
                distributions['top_rrf_score'],
                target_precision=0.90
            )
            recommendations['T_RETRIEVE_CONFIDENCE'] = threshold
            print(f"T_RETRIEVE_CONFIDENCE: {threshold:.4f} (P={metrics.get('precision', 0):.2f}, R={metrics.get('recall', 0):.2f})")
        
        # Calibrate evidence count
        if 'evidence_count' in distributions:
            # For evidence count, we want minimum needed
            counts = [int(count) for count, is_pos in distributions['evidence_count'] if is_pos]
            if counts:
                recommendations['T_EVIDENCE_COUNT_MIN'] = float(statistics.median(counts))
                print(f"T_EVIDENCE_COUNT_MIN: {statistics.median(counts)}")
        
        return recommendations


# ==============================================================================
# CLI
# ==============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="RAG Evaluation Harness")
    subparsers = parser.add_subparsers(dest='command', required=True)
    cfg = get_config()
    
    # build-testset
    build_parser = subparsers.add_parser('build-testset', help='Build test set from chunks')
    build_parser.add_argument(
        '--chunks',
        type=Path,
        default=None,
        help=f"Chunks JSONL (default: {cfg.paths.chunks_jsonl_path})",
    )
    build_parser.add_argument(
        '--output',
        type=Path,
        default=None,
        help=f"Output testset JSONL (default: {cfg.paths.base_dir / 'tests' / 'testset.jsonl'})",
    )
    build_parser.add_argument('--size', type=int, default=100)
    
    # run
    run_parser = subparsers.add_parser('run', help='Run evaluation')
    run_parser.add_argument('--testset', type=Path, required=True)
    run_parser.add_argument(
        '--output',
        type=Path,
        default=None,
        help=f"Report directory (default: {cfg.paths.reports_dir})",
    )
    run_parser.add_argument('--verbose', action='store_true')
    
    # calibrate
    cal_parser = subparsers.add_parser('calibrate', help='Calibrate thresholds')
    cal_parser.add_argument('--testset', type=Path, required=True)
    cal_parser.add_argument('--verbose', action='store_true')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    if args.command == 'build-testset':
        builder = TestSetBuilder()
        chunks_path = args.chunks or cfg.paths.chunks_jsonl_path
        out_path = args.output or (cfg.paths.base_dir / "tests" / "testset.jsonl")
        builder.build_test_set(chunks_path, out_path, args.size)
        
    elif args.command == 'run':
        evaluator = Evaluator()
        test_set = evaluator.load_test_set(args.testset)
        print(f"Loaded {len(test_set)} test cases")
        
        report = evaluator.run_evaluation(test_set, verbose=args.verbose)
        
        # Save reports
        output_dir = args.output or cfg.paths.reports_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        report.save_json(output_dir / 'latest.json')
        report.save_summary(output_dir / 'latest.txt')
        
        print(f"\nReports saved to {output_dir}/")
        print(f"\nKey metrics:")
        print(f"  Recall@10: {report.retrieval.recall_at_10:.3f}")
        print(f"  MRR:       {report.retrieval.mrr:.3f}")
        print(f"  Router:    {report.router.accuracy:.3f}")
        print(f"  p95 lat:   {report.latency.total_p95_ms:.0f}ms")
        
    elif args.command == 'calibrate':
        calibrator = ThresholdCalibrator()
        evaluator = Evaluator()
        test_set = evaluator.load_test_set(args.testset)
        print(f"Loaded {len(test_set)} test cases")
        
        recommendations = calibrator.calibrate(test_set, verbose=args.verbose)
        
        print("\nRecommended thresholds (copy to config.py):")
        for name, value in recommendations.items():
            print(f"  {name} = {value}")


if __name__ == "__main__":
    main()
