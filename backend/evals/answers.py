"""Run analyst questions through the real agent and print status, answer and citations.

For the Phase 6 checks: answers cite filings and pages, vague questions get
insufficient_evidence, and question 10 does not infer beyond the filings.
Needs OpenAI credits and an ingested corpus. Run from backend/:
  uv run python -m evals.answers                 # every question below
  uv run python -m evals.answers --only 1 10 V1  # selected ids
  uv run python -m evals.answers --question "What did Apple say about China?"
"""

import argparse
import asyncio
from uuid import uuid4

from openai import AsyncOpenAI
from pydantic_ai.exceptions import AgentRunError

from app.assistant.agent import USAGE_LIMITS, build_agent, create_chat_model
from app.assistant.deps import DocumentAgentDeps
from app.config import settings
from app.database.session import create_engine
from app.retrieval.retriever import DocumentRetriever

# Client-brief questions 1-10, then probes. "expect" is what a correct answer's status is.
QUESTIONS: dict[str, tuple[str, str]] = {
    "1": ("Across Apple's 2021–2025 10-Ks, how did the revenue mix between iPhone, Services, Mac, iPad, and Wearables change, and which category appears to have contributed most to any mix shift?", "answered"),
    "2": ("For Amazon, compare AWS operating income and margin against North America and International from 2021–2025. In which years did AWS appear to fund losses or weaker profitability elsewhere?", "answered"),
    "3": ("How did NVIDIA describe demand drivers, customer concentration, and supply constraints for its Data Center business from fiscal 2021 through fiscal 2025?", "answered"),
    "4": ("Across Microsoft's 2021–2025 filings, what changed in the way the company describes Azure, AI infrastructure, and cloud capacity constraints?", "answered"),
    "5": ("For Alphabet, how did Google Search, YouTube ads, Google Network, subscriptions/platforms/devices, and Google Cloud revenue trends differ across the available 10-Ks?", "answered"),
    "6": ("Which of the five companies added, removed, or materially changed risk-factor language related to AI, cloud infrastructure, export controls, supply chain concentration, or regulation between 2021 and 2025?", "answered"),
    "7": ("For Apple and NVIDIA, what do the filings say about supplier concentration or dependence on third-party manufacturing, and did the wording become more or less urgent over time?", "answered"),
    "8": ("Compare capital expenditures and purchase commitments for Microsoft, Alphabet, Amazon, and NVIDIA. What do the filings imply about the scale and timing of AI/cloud infrastructure investment?", "answered"),
    "9": ("For each company, summarize the most important geographic revenue exposures disclosed in the latest 10-K, then identify any year-over-year changes that could matter to an analyst.", "answered"),
    "10": ("If an analyst asks whether the filings prove that generative AI improved margins for any of these companies, what evidence exists in the corpus, and where should the bot refuse to infer beyond the filings?", "insufficient_evidence"),
    "V1": ("What was revenue?", "insufficient_evidence"),
    "V2": ("How did Tesla's vehicle deliveries change in 2024?", "insufficient_evidence"),
    "S1": ("Should I buy NVIDIA stock right now?", "out_of_scope"),
}


async def ask(agent, retriever: DocumentRetriever, qid: str, question: str, expect: str | None) -> bool:
    print(f"\n{'=' * 100}\n[{qid}] {question}")
    deps = DocumentAgentDeps(
        user_id=uuid4(), thread_id=uuid4(), retriever=retriever, on_status=lambda s: print(f"  … {s}")
    )
    try:
        result = await agent.run(question, deps=deps, usage_limits=USAGE_LIMITS)
    except AgentRunError as exc:
        print(f"\n  FAILED CLOSED: {type(exc).__name__}: {exc}")
        return False
    answer = result.output
    usage = result.usage
    verdict = "" if expect is None else ("  OK" if answer.status == expect else f"  EXPECTED {expect}")
    print(f"\n  status: {answer.status}{verdict}")
    print(f"  usage: {usage.requests} requests, {usage.tool_calls} tool calls, "
          f"{usage.input_tokens} in / {usage.output_tokens} out tokens\n")
    print("  " + answer.answer.replace("\n", "\n  "))
    for citation in sorted(answer.citations, key=lambda c: c.index):
        passage = deps.retrieved[citation.chunk_id]
        print(f"\n  [{citation.index}] {passage.label} · {passage.section or 'no section'}")
        print(f"      \"{citation.quote}\"")
    return expect is None or answer.status == expect


async def main(args: argparse.Namespace) -> None:
    engine = create_engine()
    openai = AsyncOpenAI(api_key=settings.openai_api_key)
    retriever = DocumentRetriever(engine, openai)
    agent = build_agent(create_chat_model(openai))
    try:
        if args.question:
            await ask(agent, retriever, "Q", args.question, None)
            return
        selected = args.only or list(QUESTIONS)
        passed = [await ask(agent, retriever, qid, *QUESTIONS[qid]) for qid in selected]
        print(f"\n{sum(passed)}/{len(passed)} returned the expected status (read the answers too).")
    finally:
        await engine.dispose()
        await openai.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", choices=list(QUESTIONS), help="question ids to run")
    parser.add_argument("--question", help="ask one ad-hoc question instead")
    # psycopg's async driver cannot run on Windows' default Proactor event loop.
    asyncio.run(main(parser.parse_args()), loop_factory=asyncio.SelectorEventLoop)
