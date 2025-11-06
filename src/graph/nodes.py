# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
import os
from datetime import datetime
from typing import Annotated, Literal

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.types import Command, interrupt

from src.agents import create_agent
from src.config.agents import AGENT_LLM_MAP
from src.config.configuration import Configuration
from src.llms.llm import get_llm_by_type
from src.prompts.planner_model import Plan
from src.prompts.template import apply_prompt_template
from src.tools import (
    crawl_tool,
    get_retriever_tool,
    get_web_search_tool,
    python_repl_tool,
)
from src.tools.search import LoggedTavilySearch
from src.utils.json_utils import repair_json_output

from ..config import SELECTED_SEARCH_ENGINE, SearchEngine
from .types import State

logger = logging.getLogger(__name__)


@tool
def handoff_to_planner(
    research_topic: Annotated[str, "The topic of the research task to be handed off."],
    locale: Annotated[str, "The user's detected language locale (e.g., en-US, zh-CN)."],
):
    """Handoff to planner agent to do plan."""
    # This tool is not returning anything: we're just using it
    # as a way for LLM to signal that it needs to hand off to planner agent
    return


def background_investigation_node(state: State, config: RunnableConfig):
    logger.info("background investigation node is running.")
    configurable = Configuration.from_runnable_config(config)
    query = state.get("research_topic")
    background_investigation_results = None
    if SELECTED_SEARCH_ENGINE == SearchEngine.TAVILY.value:
        searched_content = LoggedTavilySearch(
            max_results=configurable.max_search_results
        ).invoke(query)
        # check if the searched_content is a tuple, then we need to unpack it
        if isinstance(searched_content, tuple):
            searched_content = searched_content[0]
        if isinstance(searched_content, list):
            background_investigation_results = [
                f"## {elem['title']}\n\n{elem['content']}" for elem in searched_content
            ]
            return {
                "background_investigation_results": "\n\n".join(
                    background_investigation_results
                )
            }
        else:
            logger.error(
                f"Tavily search returned malformed response: {searched_content}"
            )
    else:
        background_investigation_results = get_web_search_tool(
            configurable.max_search_results
        ).invoke(query)
    return {
        "background_investigation_results": json.dumps(
            background_investigation_results, ensure_ascii=False
        )
    }


def planner_node(
    state: State, config: RunnableConfig
) -> Command[Literal["human_feedback", "reporter"]]:
    """Planner node that generate the full plan."""
    logger.info("Planner generating full plan")
    configurable = Configuration.from_runnable_config(config)
    plan_iterations = state["plan_iterations"] if state.get("plan_iterations", 0) else 0
    messages = apply_prompt_template("planner", state, configurable)

    if state.get("enable_background_investigation") and state.get(
        "background_investigation_results"
    ):
        messages += [
            {
                "role": "user",
                "content": (
                    "background investigation results of user query:\n"
                    + state["background_investigation_results"]
                    + "\n"
                ),
            }
        ]

    if configurable.enable_deep_thinking:
        llm = get_llm_by_type("reasoning")
    elif AGENT_LLM_MAP["planner"] == "basic":
        llm = get_llm_by_type("basic").with_structured_output(
            Plan,
            method="json_mode",
        )
    else:
        llm = get_llm_by_type(AGENT_LLM_MAP["planner"])

    # if the plan iterations is greater than the max plan iterations, return the reporter node
    if plan_iterations >= configurable.max_plan_iterations:
        return Command(goto="reporter")

    full_response = ""
    if AGENT_LLM_MAP["planner"] == "basic" and not configurable.enable_deep_thinking:
        response = llm.invoke(messages)
        full_response = response.model_dump_json(indent=4, exclude_none=True)
    else:
        response = llm.stream(messages)
        for chunk in response:
            full_response += chunk.content
    logger.debug(f"Current state messages: {state['messages']}")
    logger.info(f"Planner response: {full_response}")

    try:
        curr_plan = json.loads(repair_json_output(full_response))
    except json.JSONDecodeError:
        logger.warning("Planner response is not a valid JSON")
        if plan_iterations > 0:
            return Command(goto="reporter")
        else:
            return Command(goto="__end__")
    if isinstance(curr_plan, dict) and curr_plan.get("has_enough_context"):
        logger.info("Planner response has enough context.")
        new_plan = Plan.model_validate(curr_plan)
        return Command(
            update={
                "messages": [AIMessage(content=full_response, name="planner")],
                "current_plan": new_plan,
            },
            goto="reporter",
        )
    return Command(
        update={
            "messages": [AIMessage(content=full_response, name="planner")],
            "current_plan": full_response,
        },
        goto="human_feedback",
    )


def human_feedback_node(
    state,
) -> Command[Literal["planner", "research_team", "reporter", "__end__"]]:
    current_plan = state.get("current_plan", "")
    # check if the plan is auto accepted
    auto_accepted_plan = state.get("auto_accepted_plan", False)
    if not auto_accepted_plan:
        feedback = interrupt("Please Review the Plan.")

        # if the feedback is not accepted, return the planner node
        if feedback and str(feedback).upper().startswith("[EDIT_PLAN]"):
            return Command(
                update={
                    "messages": [
                        HumanMessage(content=feedback, name="feedback"),
                    ],
                },
                goto="planner",
            )
        elif feedback and str(feedback).upper().startswith("[ACCEPTED]"):
            logger.info("Plan is accepted by user.")
        else:
            raise TypeError(f"Interrupt value of {feedback} is not supported.")

    # if the plan is accepted, run the following node
    plan_iterations = state["plan_iterations"] if state.get("plan_iterations", 0) else 0
    goto = "research_team"
    try:
        current_plan = repair_json_output(current_plan)
        # increment the plan iterations
        plan_iterations += 1
        # parse the plan
        new_plan = json.loads(current_plan)
    except json.JSONDecodeError:
        logger.warning("Planner response is not a valid JSON")
        if plan_iterations > 1:  # the plan_iterations is increased before this check
            return Command(goto="reporter")
        else:
            return Command(goto="__end__")

    return Command(
        update={
            "current_plan": Plan.model_validate(new_plan),
            "plan_iterations": plan_iterations,
            "locale": new_plan["locale"],
        },
        goto=goto,
    )


def coordinator_node(
    state: State, config: RunnableConfig
) -> Command[Literal["planner", "background_investigator", "__end__"]]:
    """Coordinator node that communicate with customers."""
    logger.info("Coordinator talking.")
    configurable = Configuration.from_runnable_config(config)
    messages = apply_prompt_template("coordinator", state)
    response = (
        get_llm_by_type(AGENT_LLM_MAP["coordinator"])
        .bind_tools([handoff_to_planner])
        .invoke(messages)
    )
    logger.debug(f"Current state messages: {state['messages']}")

    goto = "__end__"
    locale = state.get("locale", "en-US")  # Default locale if not specified
    research_topic = state.get("research_topic", "")

    if len(response.tool_calls) > 0:
        goto = "planner"
        if state.get("enable_background_investigation"):
            # if the search_before_planning is True, add the web search tool to the planner agent
            goto = "background_investigator"
        try:
            for tool_call in response.tool_calls:
                if tool_call.get("name", "") != "handoff_to_planner":
                    continue
                if tool_call.get("args", {}).get("locale") and tool_call.get(
                    "args", {}
                ).get("research_topic"):
                    locale = tool_call.get("args", {}).get("locale")
                    research_topic = tool_call.get("args", {}).get("research_topic")
                    break
        except Exception as e:
            logger.error(f"Error processing tool calls: {e}")
    else:
        logger.warning(
            "Coordinator response contains no tool calls. Terminating workflow execution."
        )
        logger.debug(f"Coordinator response: {response}")
    messages = state.get("messages", [])
    if response.content:
        messages.append(HumanMessage(content=response.content, name="coordinator"))
    return Command(
        update={
            "messages": messages,
            "locale": locale,
            "research_topic": research_topic,
            "resources": configurable.resources,
        },
        goto=goto,
    )


def reporter_node(state: State, config: RunnableConfig):
    """Reporter node that write a final report."""
    logger.info("Reporter write final report")
    configurable = Configuration.from_runnable_config(config)
    current_plan = state.get("current_plan")
    
    # 兼容没有 current_plan 的情况
    if current_plan and hasattr(current_plan, 'title') and hasattr(current_plan, 'thought'):
        task_title = current_plan.title
        task_description = current_plan.thought
    else:
        # 使用 research_topic 作为备选
        task_title = state.get("research_topic", "研究任务")
        task_description = f"基于用户查询：{task_title} 进行研究和分析"
    
    input_ = {
        "messages": [
            HumanMessage(
                f"# Research Requirements\n\n## Task\n\n{task_title}\n\n## Description\n\n{task_description}"
            )
        ],
        "locale": state.get("locale", "en-US"),
    }
    invoke_messages = apply_prompt_template("reporter", input_, configurable)
    observations = state.get("observations", [])

    # Add a reminder about the new report format, citation style, and table usage
    from langchain_core.messages import SystemMessage as _SystemMessage
    invoke_messages.append(
        _SystemMessage(
            content="IMPORTANT: Structure your report according to the format in the prompt. Remember to include:\n\n1. Key Points - A bulleted list of the most important findings\n2. Overview - A brief introduction to the topic\n3. Detailed Analysis - Organized into logical sections\n4. Survey Note (optional) - For more comprehensive reports\n5. Key Citations - List all references at the end\n\nFor citations, DO NOT include inline citations in the text. Instead, place all citations in the 'Key Citations' section at the end using the format: `- [Source Title](URL)`. Include an empty line between each citation for better readability.\n\nPRIORITIZE USING MARKDOWN TABLES for data presentation and comparison. Use tables whenever presenting comparative data, statistics, features, or options. Structure tables with clear headers and aligned columns. Example table format:\n\n| Feature | Description | Pros | Cons |\n|---------|-------------|------|------|\n| Feature 1 | Description 1 | Pros 1 | Cons 1 |\n| Feature 2 | Description 2 | Pros 2 | Cons 2 |"
        )
    )

    for observation in observations:
        invoke_messages.append(
            HumanMessage(
                content=f"Below are some observations for the research task:\n\n{observation}",
                name="observation",
            )
        )
    logger.debug(f"Current invoke messages: {invoke_messages}")
    
    # 记录完整的invoke messages到日志系统
    try:
        from src.utils.request_logger import get_request_logger
        request_logger = get_request_logger()
        
        # 获取当前线程ID（从state中获取）
        thread_id = state.get("configurable", {}).get("thread_id", "unknown")
        request_id = f"{thread_id}_{datetime.now().isoformat()}"
        
        # 构建完整的prompt内容
        full_prompt = ""
        for msg in invoke_messages:
            if hasattr(msg, 'content'):
                full_prompt += f"{msg.__class__.__name__}: {msg.content}\n\n"
        
        # 记录到日志
        request_logger.log_prompt(
            request_id=request_id,
            agent_name="reporter",
            prompt=full_prompt,
            prompt_metadata={
                "node": "reporter_node",
                "total_messages": len(invoke_messages),
                "observations_count": len(observations),
            }
        )
        logger.info(f"已记录reporter invoke messages到日志系统，request_id: {request_id}")
    except Exception as e:
        logger.warning(f"记录reporter invoke messages失败: {e}")
    
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"]) 
    response_content = ""
    try:
        logger.info("Reporter开始流式生成报告...")
        for chunk in llm.stream(invoke_messages):
            if getattr(chunk, "content", None):
                response_content += chunk.content
        if not response_content:
            logger.warning("Reporter流式内容为空，尝试回退到invoke...")
            resp = llm.invoke(invoke_messages)
            response_content = getattr(resp, "content", "") or ""
            if not response_content and getattr(resp, "tool_calls", None):
                logger.warning(f"Reporter模型返回tool_calls无纯文本: {resp.tool_calls}")
                response_content = "抱歉，本次报告为空（模型尝试了工具调用输出）。"
    except Exception as e:
        logger.error(f"Reporter LLM调用异常: {e}", exc_info=True)
        response_content = f"抱歉，生成报告时出现错误: {str(e)}"

    logger.info(f"reporter response length: {len(response_content)}")

    return {
        "final_report": response_content,
        "messages": [AIMessage(content=response_content, name="reporter")],
    }

def research_team_node(state: State):
    """Research team node that collaborates on tasks."""
    logger.info("Research team is collaborating on tasks.")
    pass


async def _execute_agent_step(
    state: State, agent, agent_name: str
) -> Command[Literal["research_team"]]:
    """Helper function to execute a step using the specified agent."""
    current_plan = state.get("current_plan")
    
    # 兼容没有 current_plan 的情况
    if current_plan and hasattr(current_plan, 'title') and hasattr(current_plan, 'steps'):
        plan_title = current_plan.title
        plan_steps = current_plan.steps
    else:
        # 使用 research_topic 作为备选，创建一个简单的步骤
        plan_title = state.get("research_topic", "研究任务")
        plan_steps = []
        logger.info(f"No current_plan found, using research_topic: {plan_title}")
    
    observations = state.get("observations", [])

    # Find the first unexecuted step
    current_step = None
    completed_steps = []
    
    if plan_steps:
        for step in plan_steps:
            if not step.execution_res:
                current_step = step
                break
            else:
                completed_steps.append(step)
    else:
        # 如果没有步骤，创建一个简单的默认步骤
        from src.prompts.planner_model import Step, StepType
        current_step = Step(
            title=f"研究 {plan_title}",
            description=f"对 {plan_title} 进行深入研究和分析",
            step_type=StepType.RESEARCH,
            execution_res=None
        )
        logger.info(f"Created default step for: {current_step.title}")

    if not current_step:
        logger.warning("No unexecuted step found")
        return Command(goto="research_team")

    logger.info(f"Executing step: {current_step.title}, agent: {agent_name}")

    # Format completed steps information
    completed_steps_info = ""
    if completed_steps:
        completed_steps_info = "# Completed Research Steps\n\n"
        for i, step in enumerate(completed_steps):
            completed_steps_info += f"## Completed Step {i + 1}: {step.title}\n\n"
            completed_steps_info += f"<finding>\n{step.execution_res}\n</finding>\n\n"

    # Prepare the input for the agent with completed steps info
    agent_input = {
        "messages": [
            HumanMessage(
                content=f"# Research Topic\n\n{plan_title}\n\n{completed_steps_info}# Current Step\n\n## Title\n\n{current_step.title}\n\n## Description\n\n{current_step.description}\n\n## Locale\n\n{state.get('locale', 'en-US')}"
            )
        ]
    }

    # Add citation reminder for researcher agent
    if agent_name == "researcher":
        if state.get("resources"):
            resources_info = "**The user mentioned the following resource files:**\n\n"
            for resource in state.get("resources"):
                resources_info += f"- {resource.title} ({resource.description})\n"

            agent_input["messages"].append(
                HumanMessage(
                    content=resources_info
                    + "\n\n"
                    + "You MUST use the **local_search_tool** to retrieve the information from the resource files.",
                )
            )

        agent_input["messages"].append(
            HumanMessage(
                content="IMPORTANT: DO NOT include inline citations in the text. Instead, track all sources and include a References section at the end using link reference format. Include an empty line between each citation for better readability. Use this format for each reference:\n- [Source Title](URL)\n\n- [Another Source](URL)",
                name="system",
            )
        )

    # Invoke the agent
    default_recursion_limit = 25
    try:
        env_value_str = os.getenv("AGENT_RECURSION_LIMIT", str(default_recursion_limit))
        parsed_limit = int(env_value_str)

        if parsed_limit > 0:
            recursion_limit = parsed_limit
            logger.info(f"Recursion limit set to: {recursion_limit}")
        else:
            logger.warning(
                f"AGENT_RECURSION_LIMIT value '{env_value_str}' (parsed as {parsed_limit}) is not positive. "
                f"Using default value {default_recursion_limit}."
            )
            recursion_limit = default_recursion_limit
    except ValueError:
        raw_env_value = os.getenv("AGENT_RECURSION_LIMIT")
        logger.warning(
            f"Invalid AGENT_RECURSION_LIMIT value: '{raw_env_value}'. "
            f"Using default value {default_recursion_limit}."
        )
        recursion_limit = default_recursion_limit

    logger.info(f"Agent input: {agent_input}")
    result = await agent.ainvoke(
        input=agent_input, config={"recursion_limit": recursion_limit}
    )

    # Process the result
    response_content = result["messages"][-1].content
    logger.debug(f"{agent_name.capitalize()} full response: {response_content}")

    # Update the step with the execution result
    current_step.execution_res = response_content
    logger.info(f"Step '{current_step.title}' execution completed by {agent_name}")

    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=response_content,
                    name=agent_name,
                )
            ],
            "observations": observations + [response_content],
        },
        goto="research_team",
    )

async def _setup_and_execute_agent_step(
    state: State,
    config: RunnableConfig,
    agent_type: str,
    default_tools: list,
) -> Command[Literal["research_team"]]:
    """Helper function to set up an agent with appropriate tools and execute a step.

    This function handles the common logic for both researcher_node and coder_node:
    1. Configures MCP servers and tools based on agent type
    2. Creates an agent with the appropriate tools or uses the default agent
    3. Executes the agent on the current step

    Args:
        state: The current state
        config: The runnable config
        agent_type: The type of agent ("researcher" or "coder")
        default_tools: The default tools to add to the agent

    Returns:
        Command to update state and go to research_team
    """
    configurable = Configuration.from_runnable_config(config)
    mcp_servers = {}
    enabled_tools = {}

    # Extract MCP server configuration for this agent type
    if configurable.mcp_settings:
        for server_name, server_config in configurable.mcp_settings["servers"].items():
            if (
                server_config["enabled_tools"]
                and agent_type in server_config["add_to_agents"]
            ):
                mcp_servers[server_name] = {
                    k: v
                    for k, v in server_config.items()
                    if k in ("transport", "command", "args", "url", "env", "headers")
                }
                for tool_name in server_config["enabled_tools"]:
                    enabled_tools[tool_name] = server_name

    # Create and execute agent with MCP tools if available
    if mcp_servers:
        client = MultiServerMCPClient(mcp_servers)
        loaded_tools = default_tools[:]
        all_tools = await client.get_tools()
        for tool in all_tools:
            if tool.name in enabled_tools:
                tool.description = (
                    f"Powered by '{enabled_tools[tool.name]}'.\n{tool.description}"
                )
                loaded_tools.append(tool)
        agent = create_agent(agent_type, agent_type, loaded_tools, agent_type)
        return await _execute_agent_step(state, agent, agent_type)
    else:
        # Use default tools if no MCP servers are configured
        agent = create_agent(agent_type, agent_type, default_tools, agent_type)
        return await _execute_agent_step(state, agent, agent_type)


async def researcher_node(
    state: State, config: RunnableConfig
) -> Command[Literal["research_team"]]:
    """Researcher node that do research"""
    logger.info("Researcher node is researching.")
    configurable = Configuration.from_runnable_config(config)
    
    # 原有的工具
    tools = [get_web_search_tool(configurable.max_search_results), crawl_tool]
    
    # 添加BM25检索工具
    from src.tools.bm25_search import bm25_search_tool, bm25_health_check_tool, bm25_stats_tool, bm25_database_info_tool
    tools.extend([bm25_search_tool, bm25_health_check_tool, bm25_stats_tool, bm25_database_info_tool])
    
    # 添加RAG检索工具（如果配置了的话）
    retriever_tool = get_retriever_tool(state.get("resources", []))
    if retriever_tool:
        tools.insert(0, retriever_tool)
        
    logger.info(f"Researcher tools: {tools}")
    return await _setup_and_execute_agent_step(
        state,
        config,
        "researcher",
        tools,
    )

def _process_bm25_results(raw_results: str, query: str) -> str:
    """加工BM25搜索结果，提取文档标题和内容片段，让prompt更清晰"""
    import re
    
    # 如果搜索失败或无结果，直接返回
    if "未找到" in raw_results or "搜索服务" in raw_results:
        return raw_results
    
    try:
        # 解析搜索结果
        results = []
        current_result = {}
        
        lines = raw_results.split('\n')
        in_content_section = False
        content_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                if in_content_section:
                    content_lines.append('')
                continue
                
            # 匹配结果标题
            if line.startswith('## 结果'):
                if current_result:
                    # 保存之前的内容
                    if content_lines:
                        current_result['content'] = '\n'.join(content_lines).strip()
                    results.append(current_result)
                current_result = {}
                in_content_section = False
                content_lines = []
            elif line.startswith('**标题**:'):
                current_result['title'] = line.replace('**标题**:', '').strip()
                in_content_section = False
            elif line.startswith('**内容片段**:'):
                # 开始内容片段部分
                in_content_section = True
                content_lines = []
                # 如果标题行后面直接有内容，也要包含进来
                content_after_colon = line.replace('**内容片段**:', '').strip()
                if content_after_colon:
                    content_lines.append(content_after_colon)
            elif line.startswith('**路径**:'):
                current_result['path'] = line.replace('**路径**:', '').strip()
                in_content_section = False
            elif line.startswith('**评分**:'):
                current_result['score'] = line.replace('**评分**:', '').strip()
                in_content_section = False
            elif in_content_section:
                # 在内容片段部分，收集所有行
                content_lines.append(line)
        
        # 添加最后一个结果
        if current_result:
            # 保存最后的内容
            if content_lines:
                current_result['content'] = '\n'.join(content_lines).strip()
            results.append(current_result)
        
        # 格式化加工后的结果
        if not results:
            return f"未找到与 '{query}' 相关的文档内容"
        
        # 限制最多两个文档
        limited_results = results[:2]
        
        formatted_results = []
        formatted_results.append(f"📚 找到 {len(limited_results)} 个相关文档：")
        formatted_results.append("")
        for i, result in enumerate(limited_results, 1):
            # 使用解析出的路径作为标题，如果没有路径则使用原标题
            title = result.get('path', result.get('title', '未知标题'))
            content = result.get('content', '')
            
            formatted_results.append(f"### 文档 {i}: {title}")
            if content:
                # 清理内容片段，移除多余的空白和特殊字符
                cleaned_content = re.sub(r'\s+', ' ', content).strip()
                # 限制内容长度，避免prompt过长
                if len(cleaned_content) > 500:
                    cleaned_content = cleaned_content[:500] + "..."
                formatted_results.append(f"**内容**: {cleaned_content}")
            else:
                formatted_results.append("**内容**: 无相关内容片段")
            formatted_results.append("")
        
        return "\n".join(formatted_results)
        
    except Exception as e:
        logger.error(f"加工BM25搜索结果失败: {e}")
        # 如果加工失败，返回原始结果
        return raw_results

async def simple_researcher_node(state: State, config: RunnableConfig) -> Command[Literal["__end__"]]:
    """餐饮智能助手节点（planner 同款模式）：内部流式迭代，聚合后一次性返回。"""
    logger.info("餐饮智能助手节点运行中 (planner-style)")
    configurable = Configuration.from_runnable_config(config)

    # 1) 读取输入
    query = state.get("research_topic", "") or ""
    locale = state.get("locale", "zh-CN") or "zh-CN"
    logger.info(f"用户查询: {query}")
    logger.info(f"用户语言: {locale}")

    # 2) 先发送搜索状态消息
    search_status_message = AIMessage(
        content="🔍 正在搜索内部文档...",
        name="simple_researcher"
    )

    # 3) BM25 搜索
    search_results = ""
    found_files = []
    try:
        from src.tools.bm25_search import bm25_search_tool
        logger.info("正在执行BM25搜索...")
        search_results = bm25_search_tool.invoke(query, limit=1, include_snippets=True)
        logger.info(f"BM25搜索完成，结果长度: {len(str(search_results))}")
        logger.debug(f"BM25搜索结果: {search_results}")
        
        search_results = _process_bm25_results(search_results, query)
        logger.info(f"加工后的搜索结果: {search_results}")
        # 提取文件名（从搜索结果中解析）
        import re
        import os
        # 从搜索结果中提取路径并转换为文件名
        path_matches = re.findall(r'\*\*路径\*\*: (.+)', search_results)
        found_files = [os.path.basename(path) for path in path_matches[:1]]  # 最多显示2个文件
        
    except Exception as e:
        logger.error(f"BM25搜索失败: {e}", exc_info=True)
        search_results = f"搜索服务暂时不可用: {e}"

    # 4) 发送搜索结果消息
    
    
    files_info = ""
    if found_files:
        files_info = f"\n📄 搜索到的文件：\n" + "\n".join([f"- {file}" for file in found_files])
    else:
        files_info = "\n📄 未找到相关文件"

    search_result_message = AIMessage(
        content=f"✅ 搜索完成{files_info}",
        name="simple_researcher"
    )

    # 5) 构造提示消息（与原始一致）

#     system_content = f"""你是一个专业的餐饮智能助手，专门为餐饮行业员工和店长提供专业的解答和指导。
# 回答要求：
# 1. 内容必须真实、可验证、无事实错误。
# 2. 语言要尽量简单直接，避免使用复杂句式。
# 3. 高亮重点答案，帮助用户快速理解核心信息。
# 4. 如需补充信息，适当扩展但控制篇幅，不要冗长。
# 5. 结构清晰，有条理，优先满足用户的实际问题需求。"""
    # system_content = f"""你是一个专业的餐饮智能助手，专门为餐饮行业员工和店长提供专业的解答和指导。
    #     回答要求：
    #     1. 内容必须真实、可验证、无事实错误。
    #     2. 语言要尽量简单直接，避免使用复杂句式。
    #     3. 高亮重点答案，帮助用户快速理解核心信息。
    #     4. 如需补充信息，适当扩展但控制篇幅，不要冗长。
    #     5. 结构清晰，有条理，优先满足用户的实际问题需求。
    #     """
    # user_content = f"""
    #     1. 分析用户问题，明确其核心需求。
    #     2. 判断内部文档是否与该问题相关：
    #     - 有关：引用文档内容进行回答，不得修改原有信息（如食材用量、配方等）。
    #     - 无关：直接基于专业知识作答。
    #     3. 给出清晰、可执行的解决方案，必要时补充行业标准建议。
    #     4. 结构清晰，重点突出，语言简洁。
    #     5. 使用语言：{locale}

    #     连锁餐饮常见处理逻辑：
    #     - 出品偏差：判断偏差程度，小偏差允许标准内调整（如加汤稀释、加热保香），并记录调整原因；严重偏差立即停止出品并上报。
    #     - 食材异常：不合格拒收或停售，记录批次信息并上报总部。
    #     - 设备异常：如影响安全或出品质量，立即停售相关品项，联系维修并上报。
    #     - 顾客客诉：先安抚顾客，现场补救或记录情况，上报总部复盘。

    #     用户问题：{query}
    #     相关内部文档信息：
    #     {search_results}

    #     请基于以上信息，提供简明、准确、可落地的餐饮解决方案。
    #     """
    # user_content = f"""

    #     用户问题：{query}
    #     相关内部文档信息：
    #     {search_results}
    #     """
    system_content = f"""
You are a professional restaurant operations assistant, specialized in providing accurate and practical guidance for restaurant staff and managers.

Answer requirements:
1. All information must be factual, verifiable, and error-free.
2. Use clear and simple language, avoiding complex sentences.
3. Highlight key points to help users quickly grasp the core answer.
4. If additional information is needed, keep it concise and relevant — avoid unnecessary details.
5. Keep the structure clear and organized, focusing on solving the user's actual problem.

Formatting rules:
- Use Markdown formatting for all responses
- Use **bold** for key points
- Use bullet lists and numbered steps for procedures
- Use code blocks ``` ``` for commands, formulas, or templates
- Keep paragraphs short for readability
"""

    user_content = f"""
User Question: {query}
Relevant Internal Documents:
{search_results}
Language: {locale}


When using internal documents, quote related lines or sections clearly.
"""

    # system_content = f"""你是餐饮行业资深厨师，熟悉各类菜品操作流程、调味比例和烹饪规范。"""
    # user_content = f"""
    # 回答结构示例：
    # 1. 用户意图分析：简述用户想解决的核心问题
    # 2. 文档相关性判断：文档中是否包含相关信息
    # 3. 专业指导：
    #     - 如果文档提供了解决方案，严格引用文档
    #     - 如果文档无解，说明"文档未提供方案"，可给出一般性安全建议，但不得改变菜品味道
    # 4. 行业专业提示：解释为什么这样处理更安全/规范
    # 5. 使用语言：{locale}
    # 6. 注意：
    # - 不要建议破坏菜品原味的方法（如加水稀释高汤、随意改变调味比例）。
    # - 如果文档中没有明确解决方案，模型应说明"文档中未提供解决方案"，而不是凭经验或常识随意推测。
    # - 提供的操作建议必须遵循餐饮行业标准和食材使用规范。

    # 用户问题：{query}
    # 相关内部文档信息：
    # {search_results}

    # 请基于以上内部文档信息，为用户提供专业的餐饮解答和指导。如果文档中有相关信息，请重点引用，且不要更改文档里的内容比如盐的用量或者食材的用量；如果找不到答案，就说明文件中没有相关信息，不要编造"""
    
    from langchain_core.messages import SystemMessage as _SystemMessage
    invoke_messages = [
        _SystemMessage(content=system_content),
        HumanMessage(content=user_content),
    ]
    logger.info(f"提示消息: {user_content}")
    logger.info(f"提示消息就绪，数量: {len(invoke_messages)}")
    
    # 记录完整的invoke messages到日志系统
    try:
        from src.utils.request_logger import get_request_logger
        request_logger = get_request_logger()
        
        # 获取当前线程ID（从state中获取）
        thread_id = state.get("configurable", {}).get("thread_id", "unknown")
        request_id = f"{thread_id}_{datetime.now().isoformat()}"
        
        # 构建完整的prompt内容
        full_prompt = ""
        for msg in invoke_messages:
            if hasattr(msg, 'content'):
                full_prompt += f"{msg.__class__.__name__}: {msg.content}\n\n"
        
        # 记录到日志
        request_logger.log_prompt(
            request_id=request_id,
            agent_name="simple_researcher",
            prompt=full_prompt,
            prompt_metadata={
                "node": "simple_researcher_node",
                "system_content_length": len(system_content),
                "user_content_length": len(user_content),
                "total_messages": len(invoke_messages),
            }
        )
        logger.info(f"已记录invoke messages到日志系统，request_id: {request_id}")
    except Exception as e:
        logger.warning(f"记录invoke messages失败: {e}")

    # 6) 选择模型
    llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
    logger.info(f"开始生成专业解答，LLM: {AGENT_LLM_MAP['reporter']}")

    # 7) ✅ 修复流式输出：改用 invoke，让 LangGraph 捕获流式输出
    response_content = ""
    try:
        response = llm.invoke(invoke_messages)
        response_content = response.content if hasattr(response, 'content') else str(response)

        if not response_content:
            logger.warning("内容为空")
            response_content = "抱歉，本次回答为空。"

    except Exception as e:
        logger.error(f"LLM 调用异常: {e}", exc_info=True)
        response_content = f"抱歉，生成解答时出现错误: {e}"

    logger.info(f"simple_researcher 响应长度: {len(response_content)}")

    return Command(
        update={
            "final_report": response_content,
        }
    )


async def coder_node(
    state: State, config: RunnableConfig
) -> Command[Literal["research_team"]]:
    """Coder node that do code analysis."""
    logger.info("Coder node is coding.")
    return await _setup_and_execute_agent_step(
        state,
        config,
        "coder",
        [python_repl_tool],
    )
