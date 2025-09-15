# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
import os
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

async def simple_researcher_node(state: State, config: RunnableConfig):
    """餐饮智能助手节点，使用BM25搜索解答餐饮相关问题"""
    logger.info("餐饮智能助手节点运行中")
    
    configurable = Configuration.from_runnable_config(config)
    
    # 获取用户查询
    query = state.get("research_topic", "")
    locale = state.get("locale", "zh-CN")
    
    logger.info(f"用户查询: {query}")
    logger.info(f"用户语言: {locale}")
    
    # 使用BM25搜索获取相关信息
    search_results = ""
    try:
        from src.tools.bm25_search import bm25_search_tool
        logger.info("正在执行BM25搜索...")
        
        # 执行BM25搜索，获取更多相关结果
        search_results = bm25_search_tool.invoke(query, limit=2, include_snippets=True)
        logger.info(f"BM25搜索完成，结果长度: {len(str(search_results))}")
        logger.debug(f"BM25搜索结果: {search_results}")
        
    except Exception as e:
        logger.error(f"BM25搜索失败: {e}", exc_info=True)
        search_results = f"搜索服务暂时不可用: {str(e)}"
    
    # 生成餐饮专业解答
    logger.info("开始构建提示消息...")
    report_messages = [
        {
            "role": "system", 
            "content": f"""你是一个专业的餐饮智能助手，专门为餐饮行业提供专业的解答和指导。

你的专业领域包括：
🍽️ 菜品制作：
- 菜品SOP和标准操作程序
- 菜品制作流程和工艺标准
- 菜品配方和配料清单
- 菜品质量控制标准
- 菜品成本核算和定价
- 菜品营养分析和标签

👥 公司管理：
- 公司企业文化和价值观
- 公司组织架构和部门职责
- 公司管理制度和流程
- 公司发展战略和规划
- 公司品牌形象和宣传资料

📚 培训指导：
- 各岗位培训教材和手册
- 新员工入职培训资料
- 专业技能培训课程
- 安全操作培训指南
- 服务标准培训材料
- 管理岗位培训内容

🔧 操作流程：
- 厨房操作流程和规范
- 设备使用和维护指南
- 食品安全操作程序
- 清洁卫生标准流程
- 库存管理和采购流程
- 客户服务标准流程

回答要求：
1. 基于提供的内部文档信息进行专业解答
2. 提供具体、可操作的建议和指导
3. 使用专业但易懂的语言
4. 如果信息不足，请明确说明并提供一般性建议
5. 使用语言：{locale}
6. 结构清晰，重点突出"""
        },
        {
            "role": "user", 
            "content": f"""用户问题：{query}

相关内部文档信息：
{search_results}

请基于以上内部文档信息，为用户提供专业的餐饮解答和指导。如果文档中有相关信息，请重点引用；如果信息不足，请提供基于餐饮行业最佳实践的建议。"""
        }
    ]
    
    logger.info(f"提示消息构建完成，消息数量: {len(report_messages)}")
    
    # 生成专业解答
    final_answer = ""
    try:
        logger.info("开始调用LLM生成专业解答...")
        logger.info(f"使用的LLM类型: {AGENT_LLM_MAP['reporter']}")
        
        # 参考coordinator_node的方式，直接调用LLM
        # 将report_messages转换为LangChain消息格式
        from langchain_core.messages import SystemMessage, HumanMessage as _HumanMessage
        langchain_messages = []
        
        for msg in report_messages:
            if msg["role"] == "system":
                langchain_messages.append(SystemMessage(content=msg["content"]))
            elif msg["role"] == "user":
                langchain_messages.append(_HumanMessage(content=msg["content"]))
        
        logger.info(f"转换后的消息数量: {len(langchain_messages)}")
        # 使用流式优先，便于前端看到过程输出
        logger.info("开始直接调用LLM（流式）...")
        logger.info("---------..")
        llm = get_llm_by_type(AGENT_LLM_MAP["reporter"])
        # 尝试流式调用
        stream_success = False
        try:
            for chunk in llm.stream(langchain_messages):
                if getattr(chunk, "content", None):
                    content = chunk.content
                    if isinstance(content, str):
                        final_answer += content
            stream_success = True
        except Exception as stream_err:
            logger.info(f"LLM流式调用失败，将回退到invoke: {stream_err}")
        # 回退策略：若流式失败或无内容，则尝试非流式
        if not stream_success or not final_answer:
            logger.info("执行invoke回退策略...")
            try:
                resp = llm.invoke(langchain_messages)
                resp_content = getattr(resp, "content", None)
                final_answer = resp_content if isinstance(resp_content, str) else ""
                if not final_answer and getattr(resp, "tool_calls", None):
                    logger.warning(f"LLM返回了tool_calls且无纯文本: {resp.tool_calls}")
                    final_answer = "抱歉，本次回答为空（模型尝试了工具调用输出）。"
            except Exception as invoke_err:
                logger.error(f"LLM invoke调用也失败: {invoke_err}", exc_info=True)
                final_answer = f"抱歉，生成解答时出现错误: {str(invoke_err)}"
        
        logger.info(f"LLM调用完成，响应内容长度: {len(final_answer) if final_answer else 0}")
        
    except Exception as llm_error:
        logger.error(f"LLM调用异常: {llm_error}", exc_info=True)
        final_answer = f"抱歉，生成解答时出现错误: {str(llm_error)}"

    logger.info(f"专业解答生成完成，答案长度: {len(final_answer)}")
    logger.debug(f"生成的答案: {final_answer}")
    
    # 记录查询统计
    query_stats = {
        "query": query,
        "locale": locale,
        "search_successful": "BM25搜索" in str(search_results) and "失败" not in str(search_results),
        "answer_generated": "错误" not in final_answer,
        "search_results_length": len(str(search_results)),
        "final_answer_length": len(final_answer) if final_answer else 0
    }
    logger.info(f"查询处理完成: {query_stats}")
    
    # 返回字典格式，像reporter_node一样，这样前端就能看到流式输出了
    # return {
    #     "final_report": final_answer,
    #     "messages": [AIMessage(content=final_answer, name="reporter")],
    # }
    return {
          "final_report": final_answer,
    "messages": [AIMessage(content=final_answer, name="simple_researcher")],
        }

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
