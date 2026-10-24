"""
statistical_generator.py — Local Statistical & N-Gram Text & Metadata Synthesizer
Learns n-gram word transitions and categorical metadata distributions locally,
then generates synthetic text and matching metadata attributes.
"""

import random
import re
from collections import defaultdict, Counter


class StatisticalSynthesizer:
    """
    Fast, 100% local synthesizer using Markov n-gram chains
    and empirical metadata sampling.
    """

    def __init__(self, n_gram_size: int = 2):
        self.n_gram_size = n_gram_size
        self.transitions = defaultdict(Counter)
        self.start_words = []
        self.avg_tokens = 50
        self.std_tokens = 20
        self.titles = []
        self.metadata_distributions = defaultdict(Counter)
        self.is_fitted = False

    def _tokenize(self, text: str) -> list[str]:
        """Simple whitespace/punctuation tokenizer."""
        return re.findall(r"\b[\w'-]+\b|[.,!?;]", str(text))

    def fit(self, records: list[dict]) -> "StatisticalSynthesizer":
        """
        Learns n-gram transitions and metadata distributions from extracted records.
        """
        if not records:
            raise ValueError("Cannot fit synthesizer on empty records.")

        token_lengths = []
        for r in records:
            tokens = self._tokenize(r["target_text"])
            if len(tokens) >= 3:
                token_lengths.append(len(tokens))
                # Record start words
                self.start_words.append(tokens[: self.n_gram_size])
                # Build n-gram transition table
                for i in range(len(tokens) - self.n_gram_size):
                    prefix = tuple(tokens[i : i + self.n_gram_size])
                    next_token = tokens[i + self.n_gram_size]
                    self.transitions[prefix][next_token] += 1

            if r.get("conditioning_prompt"):
                self.titles.append(r["conditioning_prompt"])

            # Learn metadata distributions
            for k, v in r.get("context", {}).items():
                if isinstance(v, (str, int, bool)):
                    self.metadata_distributions[k][v] += 1

        if token_lengths:
            self.avg_tokens = max(15, int(sum(token_lengths) / len(token_lengths)))
        self.is_fitted = True
        return self

    def _generate_text(self, target_length: int = None) -> str:
        """Generates a novel synthetic paragraph using learned n-gram transitions."""
        if not self.start_words:
            return "Company communication update on operational status."

        length = target_length or max(15, int(random.gauss(self.avg_tokens, 15)))
        current = list(random.choice(self.start_words))
        output = list(current)

        for _ in range(length):
            prefix = tuple(current[-self.n_gram_size :])
            candidates = self.transitions.get(prefix)
            if not candidates:
                # Random restart from another valid prefix
                current = list(random.choice(self.start_words))
                continue

            words, weights = zip(*candidates.items())
            next_word = random.choices(words, weights=weights)[0]
            output.append(next_word)
            current.append(next_word)

            if next_word in [".", "!", "?"] and len(output) >= length:
                break

        # Reconstruct clean text with punctuation spacing
        text = " ".join(output)
        text = re.sub(r"\s+([.,!?;])", r"\1", text)
        return text[0].upper() + text[1:] if text else "Synthetic update."

    def _generate_context(self) -> dict:
        """Samples synthetic metadata attributes according to empirical distribution."""
        synth_context = {}
        for key, counter in self.metadata_distributions.items():
            vals, counts = zip(*counter.items())
            synth_context[key] = random.choices(vals, weights=counts)[0]
        return synth_context

    def generate(self, n_samples: int = 10, data_type: str = "email") -> list[dict]:
        """Generates n_samples of synthetic documents."""
        if not self.is_fitted:
            raise RuntimeError("Synthesizer must be fitted before generating.")

        synthetic_docs = []
        for i in range(n_samples):
            title = random.choice(self.titles) if self.titles else f"Synthetic {data_type.title()} #{i+1}"
            body = self._generate_text()
            context = self._generate_context()

            synthetic_docs.append({
                "synthetic_id": f"synth_{data_type}_{i + 1:04d}",
                "data_type": data_type,
                "title": f"[SYNTH] {title}",
                "synthetic_text": body,
                "context": context,
                "generation_method": "statistical_ngram",
            })

        return synthetic_docs
