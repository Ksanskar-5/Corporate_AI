"""Focused contract test: chatbot must abstain (not confabulate) when records
don't directly answer, and must use simple language.

Run with:  .venv/bin/python tests/test_chatbot_prompt.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.chatbot import SYSTEM_PROMPT

ABSTAIN_SENTENCE = "This information is not provided in the available records yet."


def test_abstention_sentence_present():
    assert ABSTAIN_SENTENCE in SYSTEM_PROMPT, "abstention sentence missing from prompt"


def test_no_guessing_rule():
    lowered = SYSTEM_PROMPT.lower()
    assert "do not guess" in lowered or "do not guess" in lowered.replace("-", " ")
    assert "never present uncertain" in lowered or "uncertain things as facts" in lowered


def test_simple_language_rule():
    assert "Keep language simple" in SYSTEM_PROMPT


def test_citations_only_for_direct_answers():
    assert "Claim only what the cited record actually states" in SYSTEM_PROMPT


if __name__ == "__main__":
    test_abstention_sentence_present()
    test_no_guessing_rule()
    test_simple_language_rule()
    test_citations_only_for_direct_answers()
    print("All chatbot prompt contract tests passed.")
