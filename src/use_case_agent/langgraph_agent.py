"""LangGraph workflow for controlled workflow-automation discovery."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol, TypedDict

from langchain_core.runnables import RunnableConfig

from .engine import create_case, evaluate_case, merge_candidate_patch, next_questions


class IntakeExtractionData(TypedDict):
    acknowledgement: str
    candidate_patch: dict[str, Any]
    citations: list[str]


class IntakeGraphState(TypedDict, total=False):
    case: dict[str, Any]
    user_message: str
    message_id: str
    extraction: IntakeExtractionData
    assistant_message: str
    rejected_updates: list[str]
    control_result: dict[str, Any]


class Extractor(Protocol):
    async def extract(
        self,
        *,
        message: str,
        message_id: str,
        current_case: dict[str, Any],
        planned_questions: list[dict[str, str]],
    ) -> IntakeExtractionData: ...


class QwenStructuredExtractor:
    """Structured extraction through an OpenAI-compatible Qwen endpoint."""

    def __init__(self, *, base_url: str, api_key: str, model: str, temperature: float = 0.0):
        from langchain_openai import ChatOpenAI
        from pydantic import BaseModel, Field

        class IntakeExtraction(BaseModel):
            acknowledgement: str = Field(description="One short sentence acknowledging only supplied information")
            candidate_patch: dict[str, Any] = Field(default_factory=dict)
            citations: list[str] = Field(default_factory=list)

        self._schema = IntakeExtraction
        self._model = ChatOpenAI(
            base_url=base_url.rstrip("/"),
            api_key=api_key or "not-required",
            model=model,
            temperature=temperature,
            max_retries=2,
        ).with_structured_output(IntakeExtraction)
        prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "langgraph_extraction_prompt.md"
        self._system_prompt = prompt_path.read_text(encoding="utf-8")

    @classmethod
    def from_env(cls) -> "QwenStructuredExtractor":
        base_url = os.environ.get("QWEN_BASE_URL", "").strip()
        model = os.environ.get("QWEN_MODEL", "").strip()
        if not base_url or not model:
            raise RuntimeError("QWEN_BASE_URL and QWEN_MODEL must be configured")
        return cls(
            base_url=base_url,
            api_key=os.environ.get("QWEN_API_KEY", ""),
            model=model,
            temperature=float(os.environ.get("QWEN_TEMPERATURE", "0")),
        )

    async def extract(
        self,
        *,
        message: str,
        message_id: str,
        current_case: dict[str, Any],
        planned_questions: list[dict[str, str]],
    ) -> IntakeExtractionData:
        from langchain_core.messages import HumanMessage, SystemMessage

        payload = {
            "message_reference": message_id,
            "current_user_message": message,
            "current_case": current_case,
            "deterministic_question_plan": planned_questions,
        }
        result = await self._model.ainvoke(
            [
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        return {
            "acknowledgement": result.acknowledgement,
            "candidate_patch": result.candidate_patch,
            "citations": result.citations,
        }


def _compose_response(
    acknowledgement: str,
    control_result: dict[str, Any],
    rejected_updates: list[str],
) -> str:
    parts: list[str] = []
    if acknowledgement.strip():
        parts.append(acknowledgement.strip())
    if rejected_updates:
        parts.append(
            "I did not record some proposed fields because they lacked valid evidence or were outside the controlled schema."
        )
    questions = control_result.get("next_questions", [])
    if questions:
        parts.append("Please answer the next discovery questions:")
        parts.extend(f"{index}. {item['question']}" for index, item in enumerate(questions, 1))
    else:
        score = control_result["score"]
        parts.append(
            "The discovery record is ready for process-owner review. "
            f"The current adjusted priority score is {score['adjusted_score']:.1f} of 100 "
            f"with {score['confidence']:.0%} evidence confidence. "
            f"Recommendation: {score['recommendation']}."
        )
    return "\n\n".join(parts)


def build_graph(*, checkpointer: Any, extractor: Extractor | None = None):
    """Compile the intake graph with an injected checkpointer and extractor."""
    from langgraph.graph import END, START, StateGraph

    active_extractor = extractor or QwenStructuredExtractor.from_env()

    async def ensure_case(state: IntakeGraphState, config: RunnableConfig) -> dict[str, Any]:
        if state.get("case"):
            return {}
        thread_id = str(config.get("configurable", {}).get("thread_id", "")).strip()
        if not thread_id:
            raise ValueError("A non-empty LangGraph thread_id is required")
        return {"case": create_case(thread_id)}

    async def extract_facts(state: IntakeGraphState) -> dict[str, Any]:
        case = state["case"]
        extraction = await active_extractor.extract(
            message=state["user_message"],
            message_id=state["message_id"],
            current_case=case,
            planned_questions=next_questions(case),
        )
        return {"extraction": extraction}

    async def validate_and_score(state: IntakeGraphState) -> dict[str, Any]:
        updated, rejected = merge_candidate_patch(
            state["case"], state["extraction"].get("candidate_patch", {})
        )
        return {
            "case": updated,
            "rejected_updates": rejected,
            "control_result": evaluate_case(updated),
        }

    async def compose(state: IntakeGraphState) -> dict[str, Any]:
        message = _compose_response(
            state["extraction"].get("acknowledgement", ""),
            state["control_result"],
            state.get("rejected_updates", []),
        )
        return {"assistant_message": message}

    builder = StateGraph(IntakeGraphState)
    builder.add_node("ensure_case", ensure_case)
    builder.add_node("extract_facts", extract_facts)
    builder.add_node("validate_and_score", validate_and_score)
    builder.add_node("compose_response", compose)
    builder.add_edge(START, "ensure_case")
    builder.add_edge("ensure_case", "extract_facts")
    builder.add_edge("extract_facts", "validate_and_score")
    builder.add_edge("validate_and_score", "compose_response")
    builder.add_edge("compose_response", END)
    return builder.compile(checkpointer=checkpointer)
