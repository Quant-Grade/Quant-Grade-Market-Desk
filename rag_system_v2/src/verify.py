"""
verify.py - Citation Verification Module
=========================================
Purpose: Verify that LLM responses contain valid, grounded citations.
         Ensures no hallucinated citations or unsupported claims.

Inputs:
  - LLM response text
  - Retrieved chunks that were provided as context
  - Original query

Outputs:
  - VerificationResult with pass/fail and detailed issues
  - Suggested fix (regenerate or refuse)

Failure Modes:
  - Citation format not recognized → ParseError
  - Cited chunk doesn't exist → InvalidCitation
  - Claim has no supporting text in cited chunk → UnsupportedClaim
  - Response has no citations at all → NoCitations

CRITICAL:
  - This is the LAST line of defense against hallucination
  - Fail-closed: if verification fails, DO NOT return response
  - Either regenerate with stricter prompt or refuse
"""

import re
import logging
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

from .config import get_config
from .retrieve import RetrievedChunk

logger = logging.getLogger(__name__)


# ==============================================================================
# VERIFICATION RESULT TYPES
# ==============================================================================

class VerificationStatus(Enum):
    """Overall verification status."""
    PASS = "pass"
    WARN = "warn"  # Minor issues but acceptable
    FAIL = "fail"  # Cannot trust response


class IssueType(Enum):
    """Types of citation issues."""
    NO_CITATIONS = "no_citations"
    INVALID_CITATION_FORMAT = "invalid_citation_format"
    CITATION_NOT_FOUND = "citation_not_found"
    CLAIM_UNSUPPORTED = "claim_unsupported"
    LOW_OVERLAP = "low_overlap"
    EXCESSIVE_CLAIMS = "excessive_claims"  # Many claims, few citations


class FixAction(Enum):
    """What to do when verification fails."""
    ACCEPT = "accept"  # Verification passed
    REGENERATE = "regenerate"  # Try again with stricter prompt
    REFUSE = "refuse"  # Cannot trust, refuse to answer


@dataclass
class VerificationIssue:
    """Single verification issue."""
    issue_type: IssueType
    severity: str  # "error", "warning"
    message: str
    location: Optional[str] = None  # e.g., sentence number or citation ID
    

@dataclass
class VerificationResult:
    """Complete verification result."""
    status: VerificationStatus
    fix_action: FixAction
    issues: List[VerificationIssue] = field(default_factory=list)
    stats: Dict[str, any] = field(default_factory=dict)
    
    # Details
    citations_found: List[str] = field(default_factory=list)
    valid_citations: List[str] = field(default_factory=list)
    invalid_citations: List[str] = field(default_factory=list)
    sentences_without_citations: List[str] = field(default_factory=list)
    
    def is_acceptable(self) -> bool:
        """Whether response can be returned to user."""
        return self.status in (VerificationStatus.PASS, VerificationStatus.WARN)


# ==============================================================================
# CITATION PARSER
# ==============================================================================

class CitationParser:
    """
    Parse and extract citations from LLM responses.
    
    Supported formats:
    - [CHUNK_ID]
    - [DOC:PAGE:CHILD]
    - [abc123:2:1]
    - [CHUNK_ID: docprefix:chunkprefix] (spacing after colon — common LM drift)
    """
    
    # Labelled form: inner id may contain colons; allow whitespace after "CHUNK_ID:"
    CHUNK_LABELLED = re.compile(r'\[CHUNK_ID:\s*([A-Za-z0-9_:\-]+)\]', re.IGNORECASE)
    # Pattern matches [ANYTHING_WITHOUT_SPACES] (legacy / compact ids)
    CITATION_PATTERN = re.compile(r'\[([A-Za-z0-9_:\-]+)\]')
    
    def extract_citations(self, text: str) -> List[str]:
        """Extract all citation IDs from text."""
        ids: List[str] = []
        for m in self.CHUNK_LABELLED.finditer(text):
            ids.append(m.group(1).strip())
        for m in self.CITATION_PATTERN.finditer(text):
            inner = m.group(1)
            if inner.upper() in ("CHUNK_ID", "CHUNK"):
                continue
            if inner.upper().startswith("CHUNK_ID:"):
                continue
            ids.append(inner)
        return ids
    
    def extract_citations_with_positions(self, text: str) -> List[Tuple[str, int, int]]:
        """Extract citations with their positions (id, start, end)."""
        results = []
        for match in self.CHUNK_LABELLED.finditer(text):
            results.append((match.group(1).strip(), match.start(), match.end()))
        for match in self.CITATION_PATTERN.finditer(text):
            inner = match.group(1)
            if inner.upper() in ("CHUNK_ID", "CHUNK"):
                continue
            if inner.upper().startswith("CHUNK_ID:"):
                continue
            results.append((inner, match.start(), match.end()))
        return results
    
    def split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences for citation checking.
        Simple split on sentence-ending punctuation.
        """
        # Split on . ! ? followed by space or end
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        # Filter out very short fragments
        return [s.strip() for s in sentences if len(s.strip()) > 10]
    
    def get_sentences_with_citations(self, text: str) -> List[Tuple[str, List[str]]]:
        """
        Return list of (sentence, [citation_ids]).
        """
        sentences = self.split_into_sentences(text)
        results = []
        
        for sentence in sentences:
            citations = self.extract_citations(sentence)
            results.append((sentence, citations))
            
        return results


# ==============================================================================
# OVERLAP CHECKER
# ==============================================================================

class OverlapChecker:
    """
    Check if response content is actually supported by cited chunks.
    Uses simple text overlap heuristics.
    """
    
    def __init__(self, min_overlap_ratio: float = 0.3):
        self.min_overlap_ratio = min_overlap_ratio
        
    def _normalize_text(self, text: str) -> Set[str]:
        """Normalize text to word set for comparison."""
        # Lowercase, remove punctuation, split to words
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        words = set(text.split())
        # Remove very common words
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                    'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                    'can', 'of', 'to', 'in', 'for', 'on', 'with', 'at', 'by',
                    'from', 'or', 'and', 'not', 'this', 'that', 'it', 'as'}
        return words - stopwords
    
    def check_overlap(self, claim: str, chunk_text: str) -> float:
        """
        Calculate overlap ratio between claim and chunk.
        
        Returns ratio of claim words found in chunk (0.0 to 1.0).
        """
        claim_words = self._normalize_text(claim)
        chunk_words = self._normalize_text(chunk_text)
        
        if not claim_words:
            return 1.0  # Empty claim is vacuously supported
            
        overlap = claim_words & chunk_words
        return len(overlap) / len(claim_words)
    
    def is_supported(self, claim: str, chunk_text: str) -> bool:
        """Check if claim is supported by chunk text."""
        return self.check_overlap(claim, chunk_text) >= self.min_overlap_ratio


# ==============================================================================
# MAIN VERIFIER
# ==============================================================================

class CitationVerifier:
    """
    Main verification engine.
    
    Checks:
    1. Response has citations
    2. All citations are valid (exist in provided chunks)
    3. Factual sentences have citations
    4. Cited content supports the claims
    """
    
    def __init__(self):
        self.config = get_config()
        self.parser = CitationParser()
        self.overlap_checker = OverlapChecker(
            min_overlap_ratio=self.config.citation.min_overlap_ratio
        )
        
    def _build_chunk_map(
        self, 
        chunks: List[RetrievedChunk]
    ) -> Dict[str, RetrievedChunk]:
        """Build map of citation_id -> chunk for quick lookup."""
        chunk_map = {}
        for chunk in chunks:
            cid = chunk.citation_id()
            chunk_map[cid] = chunk
            # Also add variations
            # Short form without doc prefix
            parts = cid.split(':')
            if len(parts) >= 2:
                short = ':'.join(parts[1:])
                chunk_map[short] = chunk
        return chunk_map
    
    def _is_factual_sentence(self, sentence: str) -> bool:
        """
        Heuristic: does this sentence make a factual claim?
        
        Non-factual:
        - Questions
        - "I don't know" style responses
        - Pure transitional phrases
        """
        sentence = sentence.strip()
        
        # Questions don't need citations
        if sentence.endswith('?'):
            return False
            
        # Admission of not knowing
        not_knowing = [
            "i don't know",
            "i don't have",
            "i cannot find",
            "no information",
            "not available",
            "unclear",
            "sources used:"
        ]
        lower = sentence.lower()
        for phrase in not_knowing:
            if phrase in lower:
                return False
                
        # Very short sentences are likely transitional
        if len(sentence.split()) < 5:
            return False
            
        return True
    
    def verify(
        self,
        response: str,
        chunks: List[RetrievedChunk],
        query: str,
        strict: bool = False
    ) -> VerificationResult:
        """
        Verify LLM response for citation quality.
        
        Args:
            response: LLM-generated response text
            chunks: Retrieved chunks that were provided as context
            query: Original user query
            strict: If True, any issue = FAIL
            
        Returns:
            VerificationResult with status and issues
        """
        issues = []
        chunk_map = self._build_chunk_map(chunks)
        valid_ids = set(chunk_map.keys())
        
        # Extract all citations
        all_citations = self.parser.extract_citations(response)
        unique_citations = list(set(all_citations))
        
        # Stats
        stats = {
            'total_citations': len(all_citations),
            'unique_citations': len(unique_citations),
            'chunks_provided': len(chunks)
        }
        
        # Check 1: Response has citations?
        if not all_citations:
            # Check if response actually makes claims
            sentences = self.parser.split_into_sentences(response)
            factual_sentences = [s for s in sentences if self._is_factual_sentence(s)]
            
            if factual_sentences:
                issues.append(VerificationIssue(
                    issue_type=IssueType.NO_CITATIONS,
                    severity="error",
                    message=f"Response makes {len(factual_sentences)} factual claims but has no citations"
                ))
        
        # Check 2: All citations valid?
        valid_citations = []
        invalid_citations = []
        
        for cid in unique_citations:
            if cid in valid_ids:
                valid_citations.append(cid)
            else:
                invalid_citations.append(cid)
                issues.append(VerificationIssue(
                    issue_type=IssueType.CITATION_NOT_FOUND,
                    severity="error",
                    message=f"Citation [{cid}] does not exist in provided chunks",
                    location=cid
                ))
        
        stats['valid_citations'] = len(valid_citations)
        stats['invalid_citations'] = len(invalid_citations)
        
        # Check 3: Factual sentences have citations?
        sentences_with_cites = self.parser.get_sentences_with_citations(response)
        sentences_without = []
        
        for sentence, cites in sentences_with_cites:
            if self._is_factual_sentence(sentence) and not cites:
                sentences_without.append(sentence)
        
        if sentences_without:
            # Warning if just a few, error if many
            severity = "error" if len(sentences_without) > 2 else "warning"
            issues.append(VerificationIssue(
                issue_type=IssueType.EXCESSIVE_CLAIMS,
                severity=severity,
                message=f"{len(sentences_without)} factual sentences lack citations"
            ))
        
        stats['sentences_without_citations'] = len(sentences_without)
        
        # Check 4: Claims supported by cited chunks?
        unsupported_claims = []
        
        for sentence, cites in sentences_with_cites:
            if not cites or not self._is_factual_sentence(sentence):
                continue
                
            # Check if any cited chunk supports this sentence
            supported = False
            for cid in cites:
                if cid in chunk_map:
                    chunk = chunk_map[cid]
                    if self.overlap_checker.is_supported(sentence, chunk.text):
                        supported = True
                        break
                    # Also check parent text
                    if chunk.parent_text:
                        if self.overlap_checker.is_supported(sentence, chunk.parent_text):
                            supported = True
                            break
            
            if not supported:
                unsupported_claims.append(sentence[:100])
        
        if unsupported_claims:
            issues.append(VerificationIssue(
                issue_type=IssueType.CLAIM_UNSUPPORTED,
                severity="warning",  # Heuristic-based, so warning not error
                message=f"{len(unsupported_claims)} claims may not be supported by cited chunks"
            ))
        
        stats['unsupported_claims'] = len(unsupported_claims)
        
        # Determine status and action
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        
        if strict:
            if issues:
                status = VerificationStatus.FAIL
                fix_action = FixAction.REGENERATE if error_count <= 2 else FixAction.REFUSE
            else:
                status = VerificationStatus.PASS
                fix_action = FixAction.ACCEPT
        else:
            if error_count > 2:
                status = VerificationStatus.FAIL
                fix_action = FixAction.REFUSE
            elif error_count > 0:
                status = VerificationStatus.FAIL
                fix_action = FixAction.REGENERATE
            elif warning_count > 2:
                status = VerificationStatus.WARN
                fix_action = FixAction.ACCEPT
            else:
                status = VerificationStatus.PASS
                fix_action = FixAction.ACCEPT
        
        return VerificationResult(
            status=status,
            fix_action=fix_action,
            issues=issues,
            stats=stats,
            citations_found=unique_citations,
            valid_citations=valid_citations,
            invalid_citations=invalid_citations,
            sentences_without_citations=sentences_without[:5]  # Limit for logging
        )


# ==============================================================================
# REGENERATION PROMPT
# ==============================================================================

def build_regeneration_prompt(
    original_query: str,
    original_response: str,
    issues: List[VerificationIssue]
) -> str:
    """
    Build a stricter prompt for regeneration after verification failure.
    """
    issue_summary = "\n".join([f"- {i.message}" for i in issues[:3]])
    
    return f"""Your previous response had citation issues:
{issue_summary}

Please answer again, being VERY careful to:
1. ONLY make claims that are directly stated in the reference material
2. Cite EVERY fact with [CHUNK_ID] immediately after the claim
3. If you cannot find information in the reference material, say "I don't have information about that"

Original question: {original_query}

Try again:"""


# ==============================================================================
# CLI TEST
# ==============================================================================

if __name__ == "__main__":
    import logging
    
    logging.basicConfig(level=logging.INFO)
    
    # Test verification
    verifier = CitationVerifier()
    
    # Mock chunks
    class MockChunk:
        def __init__(self, text, cid):
            self.text = text
            self.parent_text = None
            self.metadata = {}
            self._cid = cid
        def citation_id(self):
            return self._cid
    
    chunks = [
        MockChunk("Bitcoin reached $100,000 in December 2024.", "abc123:1:0"),
        MockChunk("Ethereum 2.0 uses proof of stake consensus.", "abc123:2:0"),
    ]
    
    # Test good response
    good_response = """Bitcoin hit a major milestone when it reached $100,000 [abc123:1:0]. 
Meanwhile, Ethereum has transitioned to proof of stake [abc123:2:0]."""
    
    result = verifier.verify(good_response, chunks, "What happened with crypto?")
    print(f"Good response: {result.status.value}, action: {result.fix_action.value}")
    print(f"  Issues: {len(result.issues)}")
    
    # Test bad response (no citations)
    bad_response = """Bitcoin reached $100,000. Ethereum uses proof of stake.
Solana is also very fast."""
    
    result = verifier.verify(bad_response, chunks, "What happened with crypto?")
    print(f"\nBad response: {result.status.value}, action: {result.fix_action.value}")
    for issue in result.issues:
        print(f"  - {issue.severity}: {issue.message}")
    
    # Test invalid citation
    invalid_response = """Bitcoin reached $100,000 [fake:0:0]."""
    
    result = verifier.verify(invalid_response, chunks, "What about Bitcoin?")
    print(f"\nInvalid citation: {result.status.value}, action: {result.fix_action.value}")
    for issue in result.issues:
        print(f"  - {issue.severity}: {issue.message}")
    
    print("\nVerification tests complete!")
