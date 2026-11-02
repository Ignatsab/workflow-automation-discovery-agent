"""FastAPI adapter for Langflow and direct clients."""

import hmac
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel, Field

from .langgraph_agent import Extractor, QwenStructuredExtractor, build_graph


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1, max_length=20000)
    message_id: str | None = Field(default=None, max_length=255)


class ChatResponse(BaseModel):
    thread_id: str
    assistant_message: str
    case: dict[str, Any]
    control_result: dict[str, Any]
    rejected_updates: list[str]


def _extract_langflow_fields(payload: dict[str, Any]) -> tuple[str, str, str]:
    message = str(payload.get("text") or payload.get("input_value") or "").strip()
    session_id = str(payload.get("session_id") or "").strip()
    message_id = str(payload.get("id") or payload.get("message_id") or uuid.uuid4())
    if not message:
        raise ValueError("Langflow message body does not contain text")
    if not session_id:
        raise ValueError("Langflow Chat Input must provide a unique session_id")
    return message, session_id, message_id


def create_app(*, extractor: Extractor | None = None, checkpointer: Any | None = None):
    from fastapi import Depends, FastAPI, Header, HTTPException, Request
    from fastapi.responses import JSONResponse
    from langgraph.checkpoint.memory import InMemorySaver
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        postgres_context = None
        active_checkpointer = checkpointer
        if active_checkpointer is None:
            database_url = os.environ.get("CHECKPOINT_DATABASE_URL", "").strip()
            if database_url:
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

                postgres_context = AsyncPostgresSaver.from_conn_string(database_url)
                active_checkpointer = await postgres_context.__aenter__()
                if os.environ.get("AUTO_MIGRATE_CHECKPOINTS", "false").lower() == "true":
                    await active_checkpointer.setup()
            else:
                active_checkpointer = InMemorySaver()
        active_extractor = extractor or QwenStructuredExtractor.from_env()
        app.state.graph = build_graph(checkpointer=active_checkpointer, extractor=active_extractor)
        try:
            yield
        finally:
            if postgres_context is not None:
                await postgres_context.__aexit__(None, None, None)

    app = FastAPI(
        title="Workflow Automation Discovery Agent",
        version="0.2.0",
        lifespan=lifespan,
    )

    async def authorize(x_api_key: str | None = Header(default=None)) -> None:
        expected = os.environ.get("AGENT_API_KEY", "")
        if expected and (not x_api_key or not hmac.compare_digest(expected, x_api_key)):
            raise HTTPException(status_code=401, detail="Invalid API key")

    async def invoke(thread_id: str, message: str, message_id: str) -> ChatResponse:
        result = await app.state.graph.ainvoke(
            {"user_message": message, "message_id": message_id},
            {"configurable": {"thread_id": thread_id}},
        )
        return ChatResponse(
            thread_id=thread_id,
            assistant_message=result["assistant_message"],
            case=result["case"],
            control_result=result["control_result"],
            rejected_updates=result.get("rejected_updates", []),
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/chat", response_model=ChatResponse, dependencies=[Depends(authorize)])
    async def chat(body: ChatRequest) -> ChatResponse:
        return await invoke(body.thread_id, body.message, body.message_id or str(uuid.uuid4()))

    @app.post("/langflow/chat", dependencies=[Depends(authorize)])
    async def langflow_chat(request: Request):
        """Accept Message-to-Data output and return a JSON scalar for Parser `{result}`."""
        payload = await request.json()
        try:
            message, session_id, message_id = _extract_langflow_fields(payload)
            response = await invoke(session_id, message, message_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return JSONResponse(content=response.assistant_message)

    @app.get("/v1/cases/{thread_id}", dependencies=[Depends(authorize)])
    async def get_case(thread_id: str) -> dict[str, Any]:
        snapshot = await app.state.graph.aget_state({"configurable": {"thread_id": thread_id}})
        case = snapshot.values.get("case") if snapshot.values else None
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        return case

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("use_case_agent.api:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
