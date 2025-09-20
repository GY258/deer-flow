// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { nanoid } from "nanoid";
import { toast } from "sonner";
import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

import { chatStream, generatePodcast } from "../api";
import type { Message, Resource } from "../messages";
import { mergeMessage } from "../messages";
import { parseJSON } from "../utils";

import { getChatStreamSettings } from "./settings-store";

const THREAD_ID = nanoid();

export const useStore = create<{
  responding: boolean;
  threadId: string | undefined;
  messageIds: string[];
  messages: Map<string, Message>;
  researchIds: string[];
  researchPlanIds: Map<string, string>;
  researchReportIds: Map<string, string>;
  researchActivityIds: Map<string, string[]>;
  ongoingResearchId: string | null;
  openResearchId: string | null;

  appendMessage: (message: Message) => void;
  updateMessage: (message: Message) => void;
  updateMessages: (messages: Message[]) => void;
  openResearch: (researchId: string | null) => void;
  closeResearch: () => void;
  setOngoingResearch: (researchId: string | null) => void;
}>((set) => ({
  responding: false,
  threadId: THREAD_ID,
  messageIds: [],
  messages: new Map<string, Message>(),
  researchIds: [],
  researchPlanIds: new Map<string, string>(),
  researchReportIds: new Map<string, string>(),
  researchActivityIds: new Map<string, string[]>(),
  ongoingResearchId: null,
  openResearchId: null,

  appendMessage(message: Message) {
    set((state) => {
      // 检查是否已存在相同内容的消息
      const existingMessage = Array.from(state.messages.values())
        .find(m => m.content === message.content && m.agent === message.agent);
      
      if (existingMessage) {
        console.log('🚫 Duplicate message content detected, skipping:', message.id);
        return state;
      }
      
      return {
        messageIds: [...state.messageIds, message.id],
        messages: new Map(state.messages).set(message.id, message),
      };
    });
  },
  updateMessage(message: Message) {
    set((state) => ({
      messages: new Map(state.messages).set(message.id, message),
    }));
  },
  updateMessages(messages: Message[]) {
    set((state) => {
      const newMessages = new Map(state.messages);
      messages.forEach((m) => newMessages.set(m.id, m));
      return { messages: newMessages };
    });
  },
  openResearch(researchId: string | null) {
    set({ openResearchId: researchId });
  },
  closeResearch() {
    set({ openResearchId: null });
  },
  setOngoingResearch(researchId: string | null) {
    set({ ongoingResearchId: researchId });
  },
}));

export async function sendMessage(
  content?: string,
  apiFunction?: (...args: any[]) => any,
  options?: { abortSignal?: AbortSignal; resources?: Array<Resource>; interruptFeedback?: string; enableSimpleResearch?: boolean },
) {
  console.log('🚀 sendMessage called:', {
    content: content,
    hasApiFunction: !!apiFunction,
    options: options
  });

  const { interruptFeedback, resources, abortSignal, enableSimpleResearch } = options ?? {};
  if (content != null) {
    console.log('📤 Adding user message to store');
    appendMessage({
      id: nanoid(),
      threadId: THREAD_ID,
      role: "user",
      content: content,
      contentChunks: [content],
      resources,
    });
  }

  // 如果没有传入API函数，使用默认的chatStream
  if (!apiFunction) {
    const settings = getChatStreamSettings();
    apiFunction = chatStream;
    console.log('🔧 Using default chatStream with settings:', {
      thread_id: THREAD_ID,
      enable_simple_research: enableSimpleResearch ?? false,
      settings: settings
    });
    
    const stream = chatStream(
      content ?? "[REPLAY]",
      {
        thread_id: THREAD_ID,
        interrupt_feedback: interruptFeedback,
        resources,
        auto_accepted_plan: settings.autoAcceptedPlan,
        enable_deep_thinking: settings.enableDeepThinking ?? false,
        enable_background_investigation:
          settings.enableBackgroundInvestigation ?? true,
        enable_simple_research: enableSimpleResearch ?? false,
        max_plan_iterations: settings.maxPlanIterations,
        max_step_num: settings.maxStepNum,
        max_search_results: settings.maxSearchResults,
        report_style: settings.reportStyle,
        mcp_settings: settings.mcpSettings,
      },
      { abortSignal },
    );
    console.log('🔄 Starting to process stream...');
    await processStream(stream, interruptFeedback);
  } else {
    // 使用传入的API函数
    console.log('🔧 Using custom API function');
    const stream = apiFunction(content ?? "[REPLAY]", { abortSignal });
    console.log('🔄 Starting to process custom stream...');
    await processStream(stream, interruptFeedback);
  }
}

async function processStream(stream: AsyncIterable<{ type: string; data: any }>, interruptFeedback?: string) {
  console.log('🌊 processStream started with interruptFeedback:', interruptFeedback);
  setResponding(true);
  let messageId: string | undefined;
  let eventCount = 0;
  
  try {
    for await (const event of stream) {
      eventCount++;
      const type = (event as any)?.type;
      // Defensive: normalize data
      const data = (event as any)?.data ?? {};
      console.log(`📡 Event #${eventCount}:`, {
        type,
        messageId: data?.id,
        agent: data?.agent,
        role: data?.role,
        hasContent: !!data?.content,
        hasReasoningContent: !!data?.reasoning_content,
        finishReason: data?.finish_reason,
        dataKeys: Object.keys(data ?? {})
      });
      
      // Ensure message id exists to avoid crashes in downstream logic
      messageId = data.id;
      if (!messageId) {
        messageId = nanoid();
        data.id = messageId;
        console.warn("[processStream] Generated fallback message id:", messageId);
      }
      let message: Message | undefined;
      
      if (type === "tool_call_result") {
        console.log('🔧 Processing tool_call_result:', data.tool_call_id);
        message = findMessageByToolCallId(data.tool_call_id);
        console.log('🔍 Found tool call message:', message?.id);
      } else if (messageId && !existsMessage(messageId)) {
        console.log('🆕 Creating new message:', {
          id: messageId,
          agent: data.agent,
          role: data.role
        });
        message = {
          id: messageId,
          threadId: data.thread_id ?? THREAD_ID,
          agent: data.agent,
          role: data.role,
          content: "",
          contentChunks: [],
          reasoningContent: "",
          reasoningContentChunks: [],
          isStreaming: true,
          interruptFeedback: interruptFeedback ?? undefined,
        };
        appendMessage(message);
        console.log('✅ New message added to store');
      }
      
      if (!message && messageId) {
        message = getMessage(messageId);
        console.log('📝 Retrieved existing message:', message?.id);
      }
      
      if (message) {
        console.log('🔄 Before merge:', {
          messageId: message.id,
          currentContent: message.content,
          isStreaming: message.isStreaming
        });
        
        // 检查是否已经完成且内容不为空
        if (message.finishReason === "stop" && message.content && message.content.length > 0) {
          console.log('🚫 Message already completed with content, skipping merge:', message.id);
        } else {
          try {
            message = mergeMessage(message, event as any);
          } catch (e) {
            console.error('[processStream] mergeMessage error', e, { type, id: message.id });
            message.isStreaming = false;
          }
          updateMessage(message);
        }
        
        console.log('🔄 After merge:', {
          messageId: message.id,
          newContent: message.content,
          isStreaming: message.isStreaming,
          finishReason: message.finishReason
        });
      } else {
        console.warn('⚠️ No message found for event:', { type, messageId });
      }
    }
    
    console.log(`✅ Stream processing completed. Total events: ${eventCount}`);
  } catch (error) {
    console.error('❌ Error in processStream:', error);
    toast("An error occurred while generating the response. Please try again.");
    // Update message status.
    // TODO: const isAborted = (error as Error).name === "AbortError";
    if (messageId != null) {
      const message = getMessage(messageId);
      if (message?.isStreaming) {
        console.log('🛑 Marking message as not streaming due to error');
        message.isStreaming = false;
        useStore.getState().updateMessage(message);
      }
    }
    useStore.getState().setOngoingResearch(null);
  } finally {
    console.log('🏁 processStream finished, setting responding to false');
    setResponding(false);
  }
}

function setResponding(value: boolean) {
  useStore.setState({ responding: value });
}

function existsMessage(id: string) {
  return useStore.getState().messageIds.includes(id);
}

function getMessage(id: string) {
  return useStore.getState().messages.get(id);
}

function findMessageByToolCallId(toolCallId: string) {
  return Array.from(useStore.getState().messages.values())
    .reverse()
    .find((message) => {
      if (message.toolCalls) {
        return message.toolCalls.some((toolCall) => toolCall.id === toolCallId);
      }
      return false;
    });
}

function appendMessage(message: Message) {
  console.log('📝 appendMessage called:', {
    messageId: message.id,
    agent: message.agent,
    role: message.role,
    content: message.content,
    isStreaming: message.isStreaming
  });

  if (
    message.agent === "coder" ||
    message.agent === "reporter" ||
    message.agent === "researcher"
  ) {
    console.log('🔬 Processing research-related message:', message.agent);
    if (!getOngoingResearchId()) {
      console.log('🆕 Starting new research session');
      const id = message.id;
      appendResearch(id);
      openResearch(id);
    } else {
      console.log('📊 Continuing existing research session:', getOngoingResearchId());
    }
    appendResearchActivity(message);
  }
  
  console.log('💾 Adding message to store');
  // 直接调用 store 的 appendMessage，它会处理去重
  useStore.getState().appendMessage(message);
  console.log('✅ Message added to store successfully');
}

function updateMessage(message: Message) {
  console.log('🔄 updateMessage called:', {
    messageId: message.id,
    agent: message.agent,
    isStreaming: message.isStreaming,
    content: message.content?.substring(0, 100) + (message.content?.length > 100 ? '...' : '')
  });

  if (
    getOngoingResearchId() &&
    message.agent === "reporter"  &&
    !message.isStreaming
  ) {
    console.log('🏁 Research completed, clearing ongoing research');
    useStore.getState().setOngoingResearch(null);
  }
  
  console.log('💾 Updating message in store');
  useStore.getState().updateMessage(message);
  console.log('✅ Message updated in store successfully');
}

function getOngoingResearchId() {
  return useStore.getState().ongoingResearchId;
}

function appendResearch(researchId: string) {
  console.log('🔬 appendResearch called for:', researchId);
  
  // 获取当前消息
  const currentMessage = getMessage(researchId);
  
  // 如果是 simple_researcher，不添加到 researchIds
  if (currentMessage?.agent === "simple_researcher") {
    console.log('🚫 Skipping researchIds for simple_researcher');
    return;
  }
  
  let planMessage: Message | undefined;
  const reversedMessageIds = [...useStore.getState().messageIds].reverse();
  console.log('🔍 Searching for planner message in messages:', reversedMessageIds);
  
  for (const messageId of reversedMessageIds) {
    const message = getMessage(messageId);
    console.log('🔍 Checking message:', { messageId, agent: message?.agent });
    if (message?.agent === "planner") {
      planMessage = message;
      console.log('✅ Found planner message:', planMessage.id);
      break;
    }
  }
  
  const messageIds = [researchId];
  if (planMessage) {
    messageIds.unshift(planMessage.id);
    console.log('📋 Added plan message to research:', planMessage.id);
  } else {
    console.log('⚠️ No planner message found, continuing without plan');
  }
  
  const nextState: Record<string, unknown> = {
    ongoingResearchId: researchId,
    researchIds: [...useStore.getState().researchIds, researchId],
    researchActivityIds: new Map(useStore.getState().researchActivityIds).set(
      researchId,
      messageIds,
    ),
  };
  
  if (planMessage) {
    nextState.researchPlanIds = new Map(
      useStore.getState().researchPlanIds,
    ).set(researchId, planMessage.id);
  }
  
  console.log('💾 Setting research state:', nextState);
  useStore.setState(nextState);
  console.log('✅ Research state updated successfully');
}

function appendResearchActivity(message: Message) {
  console.log('🔬 appendResearchActivity called for:', {
    messageId: message.id,
    agent: message.agent
  });
  
  const researchId = getOngoingResearchId();
  console.log('🔍 Current ongoing research ID:', researchId);
  
  if (researchId) {
    const researchActivityIds = useStore.getState().researchActivityIds;
    const current = researchActivityIds.get(researchId);
    
    if (!current) {
      console.log('⚠️ No research activity found for research ID:', researchId);
      console.log('🔍 Available research activities:', Array.from(researchActivityIds.keys()));
      return;
    }
    
    console.log('📋 Current research activities:', current);
    
    if (!current.includes(message.id)) {
      console.log('➕ Adding message to research activities');
      useStore.setState({
        researchActivityIds: new Map(researchActivityIds).set(researchId, [
          ...current,
          message.id,
        ]),
      });
      console.log('✅ Message added to research activities');
    } else {
      console.log('ℹ️ Message already in research activities');
    }
    
    if (message.agent === "reporter") {
      console.log('📊 Setting research report ID');
      useStore.setState({
        researchReportIds: new Map(useStore.getState().researchReportIds).set(
          researchId,
          message.id,
        ),
      });
      console.log('✅ Research report ID set');
    }
  } else {
    console.log('ℹ️ No ongoing research, skipping activity append');
  }
}

export function openResearch(researchId: string | null) {
  useStore.getState().openResearch(researchId);
}

export function closeResearch() {
  useStore.getState().closeResearch();
}

export async function listenToPodcast(researchId: string) {
  const planMessageId = useStore.getState().researchPlanIds.get(researchId);
  const reportMessageId = useStore.getState().researchReportIds.get(researchId);
  if (planMessageId && reportMessageId) {
    const planMessage = getMessage(planMessageId)!;
    const title = parseJSON(planMessage.content, { title: "Untitled" }).title;
    const reportMessage = getMessage(reportMessageId);
    if (reportMessage?.content) {
      appendMessage({
        id: nanoid(),
        threadId: THREAD_ID,
        role: "user",
        content: "Please generate a podcast for the above research.",
        contentChunks: [],
      });
      const podCastMessageId = nanoid();
      const podcastObject = { title, researchId };
      const podcastMessage: Message = {
        id: podCastMessageId,
        threadId: THREAD_ID,
        role: "assistant",
        agent: "podcast",
        content: JSON.stringify(podcastObject),
        contentChunks: [],
        reasoningContent: "",
        reasoningContentChunks: [],
        isStreaming: true,
      };
      appendMessage(podcastMessage);
      // Generating podcast...
      let audioUrl: string | undefined;
      try {
        audioUrl = await generatePodcast(reportMessage.content);
      } catch (e) {
        console.error(e);
        useStore.setState((state) => ({
          messages: new Map(useStore.getState().messages).set(
            podCastMessageId,
            {
              ...state.messages.get(podCastMessageId)!,
              content: JSON.stringify({
                ...podcastObject,
                error: e instanceof Error ? e.message : "Unknown error",
              }),
              isStreaming: false,
            },
          ),
        }));
        toast("An error occurred while generating podcast. Please try again.");
        return;
      }
      useStore.setState((state) => ({
        messages: new Map(useStore.getState().messages).set(podCastMessageId, {
          ...state.messages.get(podCastMessageId)!,
          content: JSON.stringify({ ...podcastObject, audioUrl }),
          isStreaming: false,
        }),
      }));
    }
  }
}

export function useResearchMessage(researchId: string) {
  return useStore(
    useShallow((state) => {
      const messageId = state.researchPlanIds.get(researchId);
      return messageId ? state.messages.get(messageId) : undefined;
    }),
  );
}

export function useMessage(messageId: string | null | undefined) {
  return useStore(
    useShallow((state) =>
      messageId ? state.messages.get(messageId) : undefined,
    ),
  );
}

export function useMessageIds() {
  return useStore(useShallow((state) => state.messageIds));
}

export function useLastInterruptMessage() {
  return useStore(
    useShallow((state) => {
      if (state.messageIds.length >= 2) {
        const lastMessage = state.messages.get(
          state.messageIds[state.messageIds.length - 1]!,
        );
        return lastMessage?.finishReason === "interrupt" ? lastMessage : null;
      }
      return null;
    }),
  );
}

export function useLastFeedbackMessageId() {
  const waitingForFeedbackMessageId = useStore(
    useShallow((state) => {
      if (state.messageIds.length >= 2) {
        const lastMessage = state.messages.get(
          state.messageIds[state.messageIds.length - 1]!,
        );
        if (lastMessage && lastMessage.finishReason === "interrupt") {
          return state.messageIds[state.messageIds.length - 2];
        }
      }
      return null;
    }),
  );
  return waitingForFeedbackMessageId;
}

export function useToolCalls() {
  return useStore(
    useShallow((state) => {
      return state.messageIds
        ?.map((id) => getMessage(id)?.toolCalls)
        .filter((toolCalls) => toolCalls != null)
        .flat();
    }),
  );
}
