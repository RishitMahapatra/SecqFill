"""
LLM-based relevance judgment — a second pass on top of embedding similarity.

Pure vector similarity can't reliably tell "shares similar jargon-heavy
phrasing" apart from "actually answers the question" in this narrow, formal
domain — e.g. a "cyber insurance coverage" question scored 0.660 against an
unrelated "security policy" answer, landing as yellow when it should be red.
This asks a local LLM a direct yes/no question as a cheap sanity check on
the embedding model's top pick, instead of trying to fix that with vector
math alone.
"""
import logging

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
JUDGE_MODEL = "mistral:7b"

logger = logging.getLogger(__name__)

# Plain YES/NO instead of JSON: smaller local models are noticeably less
# reliable at producing clean, parseable JSON than a short fixed-format
# answer, and we only need one bit of information out of this call.
_PROMPT_TEMPLATE = """You are checking whether a stored answer actually, directly addresses a question — not just whether it shares similar vocabulary or topic area.

Question: {question}

Stored answer: {answer}

Does the stored answer directly and specifically address the question? Respond with exactly one word, YES or NO, and nothing else."""


def judge_relevance(question_text: str, answer_text: str) -> bool | None:
    """
    Returns True if the local LLM judges answer_text as directly addressing
    question_text, False if it judges it as not, or None if the judgment
    couldn't be made (Ollama unreachable, or the response didn't clearly
    parse as yes/no). None means "couldn't determine" — callers should
    treat it as a no-op, not as a false negative.
    """
    prompt = _PROMPT_TEMPLATE.format(question=question_text, answer=answer_text)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": JUDGE_MODEL, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        raw = response.json().get("response", "")
    except (requests.RequestException, ValueError):
        logger.warning("judge_relevance: Ollama call failed", exc_info=True)
        return None

    normalized = raw.strip().lower()
    if normalized.startswith("yes"):
        return True
    if normalized.startswith("no"):
        return False

    logger.warning("judge_relevance: could not parse model response: %r", raw)
    return None
