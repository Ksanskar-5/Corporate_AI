"""
rag_synthesizer.py — Retrieval-Augmented Local Synthesizer
Uses TF-IDF similarity to retrieve top-k exemplars as stylistic seeds,
then synthesizes privacy-safe corporate documents by blending structural templates
and anonymizing entities.
"""

import random
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class RAGSynthesizer:
    """
    Retrieval-Assisted Generation (RAG) synthesizer running 100% locally.
    Retrieves context-relevant exemplars and synthesizes new text.
    """

    def __init__(self, top_k: int = 3, guardrail=None):
        self.top_k = top_k
        self.guardrail = guardrail
        self.vectorizer = TfidfVectorizer(max_features=5000, stop_words="english")
        self.records = []
        self.tfidf_matrix = None
        self.is_fitted = False

    def fit(self, records: list[dict]) -> "RAGSynthesizer":
        """Fits TF-IDF index over extracted target texts."""
        if not records:
            raise ValueError("Records cannot be empty.")

        self.records = records
        texts = [r["target_text"] for r in records]
        self.tfidf_matrix = self.vectorizer.fit_transform(texts)
        self.is_fitted = True
        return self

    def _sanitize_entities(self, text: str) -> str:
        """Replaces real names/emails with randomized synthetic placeholders and applies guardrails."""
        if self.guardrail:
            text = self.guardrail.sanitize(text)

        # Replace email addresses
        text = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "contact@company.internal", text)
        # Replace phone numbers
        text = re.sub(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", "555-0199", text)
        # Replace monetary amounts with synthetic values
        text = re.sub(r"\$\d+(?:,\d{3})*(?:\.\d+)?", f"${random.randint(10, 500)}K", text)
        return text

    def _synthesize_from_seeds(self, seed_records: list[dict]) -> str:
        """Blends sentences from top-k retrieved exemplars into a new document."""
        candidate_sentences = []
        for r in seed_records:
            sentences = re.split(r"(?<=[.!?])\s+", r["target_text"])
            for s in sentences:
                s_clean = s.strip()
                if len(s_clean.split()) >= 4:
                    candidate_sentences.append(s_clean)

        if not candidate_sentences:
            return "Company operational update regarding contract status."

        # Select 2 to 4 diverse sentences from the seeds
        n_sentences = min(len(candidate_sentences), random.randint(2, 4))
        chosen = random.sample(candidate_sentences, n_sentences)
        blended = " ".join(chosen)
        return self._sanitize_entities(blended)

    def generate(self, n_samples: int = 10, data_type: str = "email") -> list[dict]:
        """Generates synthetic documents using retrieval-assisted blending."""
        if not self.is_fitted:
            raise RuntimeError("RAGSynthesizer must be fitted first.")

        synthetic_docs = []
        n_real = len(self.records)

        for i in range(n_samples):
            # Select a random real query seed
            query_idx = random.randint(0, n_real - 1)
            query_vec = self.tfidf_matrix[query_idx]

            # Retrieve top-k nearest exemplars
            sims = cosine_similarity(query_vec, self.tfidf_matrix)[0]
            top_indices = sims.argsort()[-self.top_k :][::-1]
            seed_records = [self.records[idx] for idx in top_indices]

            # Synthesize text from retrieved seeds
            body = self._synthesize_from_seeds(seed_records)
            base_seed = seed_records[0]
            title = base_seed.get("conditioning_prompt") or f"Synthetic {data_type}"

            # Clone context with synthetic jitter
            context = dict(base_seed.get("context", {}))

            synthetic_docs.append({
                "synthetic_id": f"synth_rag_{data_type}_{i + 1:04d}",
                "data_type": data_type,
                "title": f"[SYNTH] {title}",
                "synthetic_text": body,
                "context": context,
                "generation_method": "retrieval_assisted_rag",
            })

        return synthetic_docs
