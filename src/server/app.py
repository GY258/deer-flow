# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import base64
import json
import logging
from typing import Annotated, List, cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from langchain_core.messages import AIMessageChunk, BaseMessage, ToolMessage
from langgraph.types import Command
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.mongodb import AsyncMongoDBSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from src.config.configuration import get_recursion_limit, get_bool_env, get_str_env
from src.config.report_style import ReportStyle
from src.config.tools import SELECTED_RAG_PROVIDER
from src.graph.builder import build_graph_with_memory, build_simple_graph_with_memory
from src.llms.llm import get_configured_llm_models
from src.podcast.graph.builder import build_graph as build_podcast_graph
from src.ppt.graph.builder import build_graph as build_ppt_graph
from src.prompt_enhancer.graph.builder import build_graph as build_prompt_enhancer_graph
from src.prose.graph.builder import build_graph as build_prose_graph
from src.rag.builder import build_retriever
from src.rag.retriever import Resource
from src.server.chat_request import (
    ChatRequest,
    EnhancePromptRequest,
    FeedbackRequest,
    FeedbackResponse,
    GeneratePodcastRequest,
    GeneratePPTRequest,
    GenerateProseRequest,
    TTSRequest,
)
from src.server.config_request import ConfigResponse
from src.server.mcp_request import MCPServerMetadataRequest, MCPServerMetadataResponse
from src.server.mcp_utils import load_mcp_tools
from src.server.rag_request import (
    RAGConfigResponse,
    RAGResourceRequest,
    RAGResourcesResponse,
)
from src.tools import VolcengineTTS
from src.graph.checkpoint import chat_stream_message
from src.utils.json_utils import sanitize_args
from src.utils.request_logger import get_request_logger

logger = logging.getLogger(__name__)

INTERNAL_SERVER_ERROR_DETAIL = "Internal Server Error"

app = FastAPI(
    title="DeerFlow API",
    description="API for Deer",
    version="0.1.0",
)

# Add CORS middleware
# It's recommended to load the allowed origins from an environment variable
# for better security and flexibility across different environments.
allowed_origins_str = get_str_env("ALLOWED_ORIGINS", "http://localhost:3000")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

logger.info(f"Allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Restrict to specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Use the configured list of methods
    allow_headers=["*"],  # Now allow all headers, but can be restricted further
)
in_memory_store = InMemoryStore()
graph = build_graph_with_memory()
simple_graph = build_simple_graph_with_memory()

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    # Check if MCP server configuration is enabled
    mcp_enabled = get_bool_env("ENABLE_MCP_SERVER_CONFIGURATION", False)

    # Validate MCP settings if provided
    if request.mcp_settings and not mcp_enabled:
        raise HTTPException(
            status_code=403,
            detail="MCP server configuration is disabled. Set ENABLE_MCP_SERVER_CONFIGURATION=true to enable MCP features.",
        )

    thread_id = request.thread_id
    if thread_id == "__default__":
        thread_id = str(uuid4())

    selected_graph = simple_graph if request.enable_simple_research else graph
    
    # 记录请求日志
    request_logger = get_request_logger()
    messages = request.model_dump()["messages"]
    user_query = messages[-1]["content"] if messages else ""
    
    request_metadata = {
        "max_plan_iterations": request.max_plan_iterations,
        "max_step_num": request.max_step_num,
        "max_search_results": request.max_search_results,
        "enable_simple_research": request.enable_simple_research,
        "enable_background_investigation": request.enable_background_investigation,
        "report_style": request.report_style.value if request.report_style else None,
        "enable_deep_thinking": request.enable_deep_thinking,
        "auto_accepted_plan": request.auto_accepted_plan,
    }
    
    request_id = request_logger.log_request(
        thread_id=thread_id,
        user_query=user_query,
        messages=messages,
        request_metadata=request_metadata,
    )
    
    return StreamingResponse(
        _astream_workflow_generator(
            messages,
            thread_id,
            request.resources,
            request.max_plan_iterations,
            request.max_step_num,
            request.max_search_results,
            request.auto_accepted_plan,
            request.interrupt_feedback,
            request.mcp_settings if mcp_enabled else {},
            request.enable_background_investigation,
            request.report_style,
            request.enable_deep_thinking,
            selected_graph,
            request_id,
        ),
        media_type="text/event-stream",
    )


def _process_tool_call_chunks(tool_call_chunks):
    """Process tool call chunks and sanitize arguments."""
    chunks = []
    for chunk in tool_call_chunks:
        chunks.append(
            {
                "name": chunk.get("name", ""),
                "args": sanitize_args(chunk.get("args", "")),
                "id": chunk.get("id", ""),
                "index": chunk.get("index", 0),
                "type": chunk.get("type", ""),
            }
        )
    return chunks


def _get_agent_name(agent, message_metadata):
    """Extract agent name from agent tuple."""
    agent_name = "unknown"
    if agent and len(agent) > 0:
        agent_name = agent[0].split(":")[0] if ":" in agent[0] else agent[0]
    else:
        agent_name = message_metadata.get("langgraph_node", "unknown")
    return agent_name


def _create_event_stream_message(
    message_chunk, message_metadata, thread_id, agent_name
):
    """Create base event stream message."""
    event_stream_message = {
        "thread_id": thread_id,
        "agent": agent_name,
        "id": message_chunk.id,
        "role": "assistant",
        "checkpoint_ns": message_metadata.get("checkpoint_ns", ""),
        "langgraph_node": message_metadata.get("langgraph_node", ""),
        "langgraph_path": message_metadata.get("langgraph_path", ""),
        "langgraph_step": message_metadata.get("langgraph_step", ""),
        "content": message_chunk.content,
    }

    # Add optional fields
    if message_chunk.additional_kwargs.get("reasoning_content"):
        event_stream_message["reasoning_content"] = message_chunk.additional_kwargs[
            "reasoning_content"
        ]

    if message_chunk.response_metadata.get("finish_reason"):
        event_stream_message["finish_reason"] = message_chunk.response_metadata.get(
            "finish_reason"
        )

    return event_stream_message


def _create_interrupt_event(thread_id, event_data):
    """Create interrupt event."""
    return _make_event(
        "interrupt",
        {
            "thread_id": thread_id,
            "id": event_data["__interrupt__"][0].ns[0],
            "role": "assistant",
            "content": event_data["__interrupt__"][0].value,
            "finish_reason": "interrupt",
            "options": [
                {"text": "Edit plan", "value": "edit_plan"},
                {"text": "Start research", "value": "accepted"},
            ],
        },
    )


def _process_initial_messages(message, thread_id):
    """Process initial messages and yield formatted events."""
    json_data = json.dumps(
        {
            "thread_id": thread_id,
            "id": "run--" + message.get("id", uuid4().hex),
            "role": "user",
            "content": message.get("content", ""),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    chat_stream_message(
        thread_id, f"event: message_chunk\ndata: {json_data}\n\n", "none"
    )


async def _process_message_chunk(message_chunk, message_metadata, thread_id, agent):
    """Process a single message chunk and yield appropriate events."""
    agent_name = _get_agent_name(agent, message_metadata)
    event_stream_message = _create_event_stream_message(
        message_chunk, message_metadata, thread_id, agent_name
    )

    if isinstance(message_chunk, ToolMessage):
        # Tool Message - Return the result of the tool call
        event_stream_message["tool_call_id"] = message_chunk.tool_call_id
        yield _make_event("tool_call_result", event_stream_message)
    elif isinstance(message_chunk, AIMessageChunk):
        # AI Message - Raw message tokens
        if message_chunk.tool_calls:
            # AI Message - Tool Call
            event_stream_message["tool_calls"] = message_chunk.tool_calls
            event_stream_message["tool_call_chunks"] = message_chunk.tool_call_chunks
            event_stream_message["tool_call_chunks"] = _process_tool_call_chunks(
                message_chunk.tool_call_chunks
            )
            yield _make_event("tool_calls", event_stream_message)
        elif message_chunk.tool_call_chunks:
            # AI Message - Tool Call Chunks
            event_stream_message["tool_call_chunks"] = _process_tool_call_chunks(
                message_chunk.tool_call_chunks
            )
            yield _make_event("tool_call_chunks", event_stream_message)
        else:
            # AI Message - Raw message tokens
            yield _make_event("message_chunk", event_stream_message)
    else:
        # Fallback: handle non-chunk BaseMessage (e.g., nodes that append AIMessage at once)
        # Ensure the frontend treats this as a completed message
        if "finish_reason" not in event_stream_message:
            event_stream_message["finish_reason"] = "stop"
        yield _make_event("message_chunk", event_stream_message)


async def _stream_graph_events(
    graph_instance, workflow_input, workflow_config, thread_id
):
    """Stream events from the graph and process them."""
    async for agent, _, event_data in graph_instance.astream(
        workflow_input,
        config=workflow_config,
        stream_mode=["messages", "updates"],
        subgraphs=True,
    ):
        if isinstance(event_data, dict):
            if "__interrupt__" in event_data:
                yield _create_interrupt_event(thread_id, event_data)
            continue

        message_chunk, message_metadata = cast(
            tuple[BaseMessage, dict[str, any]], event_data
        )

        async for event in _process_message_chunk(
            message_chunk, message_metadata, thread_id, agent
        ):
            yield event


async def _astream_workflow_generator(
    messages: List[dict],
    thread_id: str,
    resources: List[Resource],
    max_plan_iterations: int,
    max_step_num: int,
    max_search_results: int,
    auto_accepted_plan: bool,
    interrupt_feedback: str,
    mcp_settings: dict,
    enable_background_investigation: bool,
    report_style: ReportStyle,
    enable_deep_thinking: bool,
    graph_instance= None,
    request_id: str = None,
):
    # 获取日志记录器
    request_logger = get_request_logger() if request_id else None
    
    # 用于收集中间结果和最终结果
    intermediate_results = []
    final_result = ""
    
    try:
        # Process initial messages
        for message in messages:
            if isinstance(message, dict) and "content" in message:
                _process_initial_messages(message, thread_id)

        # Prepare workflow input
        workflow_input = {
            "messages": messages,
            "plan_iterations": 0,
            "final_report": "",
            "current_plan": None,
            "observations": [],
            "auto_accepted_plan": auto_accepted_plan,
            "enable_background_investigation": enable_background_investigation,
            "research_topic": messages[-1]["content"] if messages else "",
        }

        if not auto_accepted_plan and interrupt_feedback:
            resume_msg = f"[{interrupt_feedback}]"
            if messages:
                resume_msg += f" {messages[-1]['content']}"
            workflow_input = Command(resume=resume_msg)

        # Prepare workflow config
        workflow_config = {
            "thread_id": thread_id,
            "resources": resources,
            "max_plan_iterations": max_plan_iterations,
            "max_step_num": max_step_num,
            "max_search_results": max_search_results,
            "mcp_settings": mcp_settings,
            "report_style": report_style.value,
            "enable_deep_thinking": enable_deep_thinking,
            "recursion_limit": get_recursion_limit(),
        }
        # 使用传入的graph_instance，如果没有则使用默认graph
        selected_graph = graph_instance or graph

        checkpoint_saver = get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False)
        checkpoint_url = get_str_env("LANGGRAPH_CHECKPOINT_DB_URL", "")
        # Handle checkpointer if configured
        connection_kwargs = {
            "autocommit": True,
            "row_factory": "dict_row",
            "prepare_threshold": 0,
        }
        if checkpoint_saver and checkpoint_url != "":
            if checkpoint_url.startswith("postgresql://"):
                logger.info("start async postgres checkpointer.")
                async with AsyncConnectionPool(
                    checkpoint_url, kwargs=connection_kwargs
                ) as conn:
                    checkpointer = AsyncPostgresSaver(conn)
                    await checkpointer.setup()
                    selected_graph.checkpointer = checkpointer
                    selected_graph.store = in_memory_store
                    async for event in _stream_graph_events(
                        graph, workflow_input, workflow_config, thread_id
                    ):
                        # 记录prompts和中间结果
                        if request_logger:
                            _log_event_data(request_logger, request_id, event, intermediate_results)
                        yield event

            if checkpoint_url.startswith("mongodb://"):
                logger.info("start async mongodb checkpointer.")
                async with AsyncMongoDBSaver.from_conn_string(
                    checkpoint_url
                ) as checkpointer:
                    selected_graph.checkpointer = checkpointer
                    selected_graph.store = in_memory_store
                    async for event in _stream_graph_events(
                        graph, workflow_input, workflow_config, thread_id
                    ):
                        # 记录prompts和中间结果
                        if request_logger:
                            _log_event_data(request_logger, request_id, event, intermediate_results)
                        yield event
        else:
            # Use graph without MongoDB checkpointer
            async for event in _stream_graph_events(
                selected_graph, workflow_input, workflow_config, thread_id
            ):
                # 记录prompts和中间结果
                if request_logger:
                    _log_event_data(request_logger, request_id, event, intermediate_results)
                    
                    # 收集最终结果
                    if "final_report" in str(event):
                        try:
                            event_str = event.split("data: ")[1] if "data: " in event else event
                            event_data = json.loads(event_str)
                            if "content" in event_data and event_data.get("finish_reason") == "stop":
                                final_result = event_data["content"]
                        except (json.JSONDecodeError, IndexError, AttributeError):
                            pass
                
                yield event
        
        # 记录最终响应
        if request_logger and request_id:
            # 如果final_result为空，尝试从intermediate_results中提取
            if not final_result and intermediate_results:
                for result in reversed(intermediate_results):
                    if result.get("content") and result.get("finish_reason") == "stop":
                        final_result = result["content"]
                        break
            
            request_logger.log_response(
                request_id=request_id,
                final_result=final_result,
                intermediate_results=intermediate_results[-20:] if len(intermediate_results) > 20 else intermediate_results,  # 只保存最后20条中间结果
                response_metadata={
                    "total_events": len(intermediate_results),
                }
            )
    
    except Exception as e:
        # 记录错误
        if request_logger and request_id:
            request_logger.log_error(
                request_id=request_id,
                error_message=str(e),
                error_details={
                    "error_type": type(e).__name__,
                    "thread_id": thread_id,
                }
            )
        raise


def _log_event_data(request_logger, request_id: str, event: str, intermediate_results: list):
    """
    记录事件数据到日志
    """
    try:
        # 解析事件
        if "data: " in event:
            event_parts = event.split("\n")
            event_type = ""
            event_data = None
            
            for part in event_parts:
                if part.startswith("event: "):
                    event_type = part[7:].strip()
                elif part.startswith("data: "):
                    try:
                        event_data = json.loads(part[6:])
                    except json.JSONDecodeError:
                        continue
            
            if event_data:
                # 记录AI消息内容（可能包含prompt）
                if event_type == "message_chunk" and "content" in event_data:
                    content = event_data["content"]
                    agent_name = event_data.get("agent", "unknown")
                    
                    # 如果内容很长，可能是prompt或重要输出
                    if len(content) > 100:
                        request_logger.log_prompt(
                            request_id=request_id,
                            agent_name=agent_name,
                            prompt=content,
                            prompt_metadata={
                                "event_type": event_type,
                                "langgraph_node": event_data.get("langgraph_node", ""),
                                "checkpoint_ns": event_data.get("checkpoint_ns", ""),
                            }
                        )
                    
                    # 收集中间结果
                    intermediate_results.append({
                        "agent": agent_name,
                        "content": content,
                        "finish_reason": event_data.get("finish_reason", ""),
                        "timestamp": event_data.get("timestamp", ""),
                    })
                
                # 记录工具调用
                elif event_type == "tool_calls" and "tool_calls" in event_data:
                    for tool_call in event_data["tool_calls"]:
                        request_logger.log_prompt(
                            request_id=request_id,
                            agent_name=event_data.get("agent", "unknown"),
                            prompt=f"Tool Call: {tool_call.get('name', 'unknown')}\nArgs: {json.dumps(tool_call.get('args', {}), ensure_ascii=False)}",
                            prompt_metadata={
                                "event_type": "tool_call",
                                "tool_name": tool_call.get("name", "unknown"),
                            }
                        )
    
    except Exception as e:
        logger.debug(f"Failed to log event data: {e}")


def _make_event(event_type: str, data: dict[str, any]):
    if data.get("content") == "":
        data.pop("content")
    # Ensure JSON serialization with proper encoding
     # 添加详细的日志记录
    thread_id = data.get("thread_id", "unknown")
    agent = data.get("agent", "unknown")
    message_id = data.get("id", "unknown")
    content_preview = ""
    
    if "content" in data and data["content"]:
        content_preview = str(data["content"])[:100] + "..." if len(str(data["content"])) > 100 else str(data["content"])
    
    logger.info(
        f"🚀 Sending event to frontend - "
        f"Type: {event_type}, "
        f"Thread: {thread_id}, "
        f"Agent: {agent}, "
        f"MessageID: {message_id}, "
        f"Content: {content_preview}"
    )
    
    # 打印完整的消息数据用于调试

    
    try:
        json_data = json.dumps(data, ensure_ascii=False)

        finish_reason = data.get("finish_reason", "")
        chat_stream_message(
            data.get("thread_id", ""),
            f"event: {event_type}\ndata: {json_data}\n\n",
            finish_reason,
        )

        return f"event: {event_type}\ndata: {json_data}\n\n"
    except (TypeError, ValueError) as e:
        logger.error(f"Error serializing event data: {e}")
        # Return a safe error event
        error_data = json.dumps({"error": "Serialization failed"}, ensure_ascii=False)
        return f"event: error\ndata: {error_data}\n\n"


@app.post("/api/tts")
async def text_to_speech(request: TTSRequest):
    """Convert text to speech using volcengine TTS API."""
    app_id = get_str_env("VOLCENGINE_TTS_APPID", "")
    if not app_id:
        raise HTTPException(status_code=400, detail="VOLCENGINE_TTS_APPID is not set")
    access_token = get_str_env("VOLCENGINE_TTS_ACCESS_TOKEN", "")
    if not access_token:
        raise HTTPException(
            status_code=400, detail="VOLCENGINE_TTS_ACCESS_TOKEN is not set"
        )

    try:
        cluster = get_str_env("VOLCENGINE_TTS_CLUSTER", "volcano_tts")
        voice_type = get_str_env("VOLCENGINE_TTS_VOICE_TYPE", "BV700_V2_streaming")

        tts_client = VolcengineTTS(
            appid=app_id,
            access_token=access_token,
            cluster=cluster,
            voice_type=voice_type,
        )
        # Call the TTS API
        result = tts_client.text_to_speech(
            text=request.text[:1024],
            encoding=request.encoding,
            speed_ratio=request.speed_ratio,
            volume_ratio=request.volume_ratio,
            pitch_ratio=request.pitch_ratio,
            text_type=request.text_type,
            with_frontend=request.with_frontend,
            frontend_type=request.frontend_type,
        )

        if not result["success"]:
            raise HTTPException(status_code=500, detail=str(result["error"]))

        # Decode the base64 audio data
        audio_data = base64.b64decode(result["audio_data"])

        # Return the audio file
        return Response(
            content=audio_data,
            media_type=f"audio/{request.encoding}",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=tts_output.{request.encoding}"
                )
            },
        )

    except Exception as e:
        logger.exception(f"Error in TTS endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/podcast/generate")
async def generate_podcast(request: GeneratePodcastRequest):
    try:
        report_content = request.content
        print(report_content)
        workflow = build_podcast_graph()
        final_state = workflow.invoke({"input": report_content})
        audio_bytes = final_state["output"]
        return Response(content=audio_bytes, media_type="audio/mp3")
    except Exception as e:
        logger.exception(f"Error occurred during podcast generation: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/ppt/generate")
async def generate_ppt(request: GeneratePPTRequest):
    try:
        report_content = request.content
        print(report_content)
        workflow = build_ppt_graph()
        final_state = workflow.invoke({"input": report_content})
        generated_file_path = final_state["generated_file_path"]
        with open(generated_file_path, "rb") as f:
            ppt_bytes = f.read()
        return Response(
            content=ppt_bytes,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    except Exception as e:
        logger.exception(f"Error occurred during ppt generation: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/prose/generate")
async def generate_prose(request: GenerateProseRequest):
    try:
        sanitized_prompt = request.prompt.replace("\r\n", "").replace("\n", "")
        logger.info(f"Generating prose for prompt: {sanitized_prompt}")
        workflow = build_prose_graph()
        events = workflow.astream(
            {
                "content": request.prompt,
                "option": request.option,
                "command": request.command,
            },
            stream_mode="messages",
            subgraphs=True,
        )
        return StreamingResponse(
            (f"data: {event[0].content}\n\n" async for _, event in events),
            media_type="text/event-stream",
        )
    except Exception as e:
        logger.exception(f"Error occurred during prose generation: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/prompt/enhance")
async def enhance_prompt(request: EnhancePromptRequest):
    try:
        sanitized_prompt = request.prompt.replace("\r\n", "").replace("\n", "")
        logger.info(f"Enhancing prompt: {sanitized_prompt}")

        # Convert string report_style to ReportStyle enum
        report_style = None
        if request.report_style:
            try:
                # Handle both uppercase and lowercase input
                style_mapping = {
                    "ACADEMIC": ReportStyle.ACADEMIC,
                    "POPULAR_SCIENCE": ReportStyle.POPULAR_SCIENCE,
                    "NEWS": ReportStyle.NEWS,
                    "SOCIAL_MEDIA": ReportStyle.SOCIAL_MEDIA,
                }
                report_style = style_mapping.get(
                    request.report_style.upper(), ReportStyle.ACADEMIC
                )
            except Exception:
                # If invalid style, default to ACADEMIC
                report_style = ReportStyle.ACADEMIC
        else:
            report_style = ReportStyle.ACADEMIC

        workflow = build_prompt_enhancer_graph()
        final_state = workflow.invoke(
            {
                "prompt": request.prompt,
                "context": request.context,
                "report_style": report_style,
            }
        )
        return {"result": final_state["output"]}
    except Exception as e:
        logger.exception(f"Error occurred during prompt enhancement: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/mcp/server/metadata", response_model=MCPServerMetadataResponse)
async def mcp_server_metadata(request: MCPServerMetadataRequest):
    """Get information about an MCP server."""
    # Check if MCP server configuration is enabled
    if not get_bool_env("ENABLE_MCP_SERVER_CONFIGURATION", False):
        raise HTTPException(
            status_code=403,
            detail="MCP server configuration is disabled. Set ENABLE_MCP_SERVER_CONFIGURATION=true to enable MCP features.",
        )

    try:
        # Set default timeout with a longer value for this endpoint
        timeout = 300  # Default to 300 seconds for this endpoint

        # Use custom timeout from request if provided
        if request.timeout_seconds is not None:
            timeout = request.timeout_seconds

        # Load tools from the MCP server using the utility function
        tools = await load_mcp_tools(
            server_type=request.transport,
            command=request.command,
            args=request.args,
            url=request.url,
            env=request.env,
            headers=request.headers,
            timeout_seconds=timeout,
        )

        # Create the response with tools
        response = MCPServerMetadataResponse(
            transport=request.transport,
            command=request.command,
            args=request.args,
            url=request.url,
            env=request.env,
            headers=request.headers,
            tools=tools,
        )

        return response
    except Exception as e:
        logger.exception(f"Error in MCP server metadata endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.get("/api/rag/config", response_model=RAGConfigResponse)
async def rag_config():
    """Get the config of the RAG."""
    return RAGConfigResponse(provider=SELECTED_RAG_PROVIDER)


@app.get("/api/rag/resources", response_model=RAGResourcesResponse)
async def rag_resources(request: Annotated[RAGResourceRequest, Query()]):
    """Get the resources of the RAG."""
    retriever = build_retriever()
    if retriever:
        return RAGResourcesResponse(resources=retriever.list_resources(request.query))
    return RAGResourcesResponse(resources=[])


@app.get("/api/config", response_model=ConfigResponse)
async def config():
    """Get the config of the server."""
    return ConfigResponse(
        rag=RAGConfigResponse(provider=SELECTED_RAG_PROVIDER),
        models=get_configured_llm_models(),
    )


@app.post("/api/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest):
    """Submit user feedback for a message."""
    try:
        request_logger = get_request_logger()
        
        # 构建请求ID - 使用thread_id和当前时间戳
        from datetime import datetime
        request_id = f"{request.thread_id}_{datetime.now().isoformat()}"
        
        # 记录用户反馈到日志系统
        request_logger.log_feedback(
            request_id=request_id,
            user_feedback=request.feedback_type,
            feedback_type="rating",
            message_id=request.message_id,
            agent_name=request.agent_name or "unknown",
            feedback_metadata={
                "thread_id": request.thread_id,
                "user_query": request.user_query,
                "feedback_text": request.feedback_text,
                "additional_info": request.additional_info or {},
                "timestamp": datetime.now().isoformat(),
            }
        )
        
        logger.info(f"User feedback received: {request.feedback_type} for message: {request.message_id}")
        
        return FeedbackResponse(
            success=True,
            message="Feedback recorded successfully"
        )
        
    except Exception as e:
        logger.error(f"Error recording feedback: {e}")
        return FeedbackResponse(
            success=False,
            message=f"Error recording feedback: {str(e)}"
        )

