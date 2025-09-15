// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import type {
  ChatEvent,
  InterruptEvent,
  MessageChunkEvent,
  ToolCallChunksEvent,
  ToolCallResultEvent,
  ToolCallsEvent,
} from "../api";
import { deepClone } from "../utils/deep-clone";

import type { Message } from "./types";

export function mergeMessage(message: Message, event: ChatEvent) {
  console.log('🔄 mergeMessage called:', {
    eventType: event.type,
    messageId: message.id,
    agent: message.agent,
    currentContent: message.content,
    eventData: event.data
  });

  if (event.type === "message_chunk") {
    console.log('📝 Processing message_chunk');
    mergeTextMessage(message, event);
  } else if (event.type === "tool_calls" || event.type === "tool_call_chunks") {
    console.log('🔧 Processing tool_calls/tool_call_chunks');
    mergeToolCallMessage(message, event);
  } else if (event.type === "tool_call_result") {
    console.log('🔧 Processing tool_call_result');
    mergeToolCallResultMessage(message, event);
  } else if (event.type === "interrupt") {
    console.log('⏸️ Processing interrupt');
    mergeInterruptMessage(message, event);
  } else {
    console.log('❓ Unknown event type:', (event as any).type);
  }
  
  if (event.data.finish_reason) {
    console.log('🏁 Processing finish_reason:', event.data.finish_reason);
    message.finishReason = event.data.finish_reason;
    message.isStreaming = false;
    if (message.toolCalls) {
      message.toolCalls.forEach((toolCall) => {
        if (toolCall.argsChunks?.length) {
          toolCall.args = JSON.parse(toolCall.argsChunks.join(""));
          delete toolCall.argsChunks;
        }
      });
    }
  }

  console.log('✅ mergeMessage completed:', {
    messageId: message.id,
    agent: message.agent,
    finalContent: message.content,
    isStreaming: message.isStreaming,
    finishReason: message.finishReason
  });

  return deepClone(message);
}

function mergeTextMessage(message: Message, event: MessageChunkEvent) {
  console.log('📝 mergeTextMessage:', {
    messageId: message.id,
    contentBefore: message.content,
    newContent: event.data.content,
    reasoningContentBefore: message.reasoningContent,
    newReasoningContent: event.data.reasoning_content
  });

  if (event.data.content) {
    message.content += event.data.content;
    message.contentChunks.push(event.data.content);
    console.log('📝 Added content chunk:', {
      newContent: event.data.content,
      totalLength: message.content.length,
      chunksCount: message.contentChunks.length
    });
  }
  if (event.data.reasoning_content) {
    message.reasoningContent = (message.reasoningContent ?? "") + event.data.reasoning_content;
    message.reasoningContentChunks = message.reasoningContentChunks ?? [];
    message.reasoningContentChunks.push(event.data.reasoning_content);
    console.log('🧠 Added reasoning content chunk:', {
      newReasoningContent: event.data.reasoning_content,
      totalLength: message.reasoningContent?.length || 0,
      chunksCount: message.reasoningContentChunks.length
    });
  }

  console.log('📝 mergeTextMessage completed:', {
    messageId: message.id,
    contentAfter: message.content,
    reasoningContentAfter: message.reasoningContent
  });
}
function convertToolChunkArgs(args: string) {
  // Convert escaped characters in args
  if (!args) return "";
  return args.replace(/&#91;/g, "[").replace(/&#93;/g, "]").replace(/&#123;/g, "{").replace(/&#125;/g, "}");
}
function mergeToolCallMessage(
  message: Message,
  event: ToolCallsEvent | ToolCallChunksEvent,
) {
  if (event.type === "tool_calls" && event.data.tool_calls[0]?.name) {
    message.toolCalls = event.data.tool_calls.map((raw) => ({
      id: raw.id,
      name: raw.name,
      args: raw.args,
      result: undefined,
    }));
  }

  message.toolCalls ??= [];
  for (const chunk of event.data.tool_call_chunks) {
    if (chunk.id) {
      const toolCall = message.toolCalls.find(
        (toolCall) => toolCall.id === chunk.id,
      );
      if (toolCall) {
        toolCall.argsChunks = [convertToolChunkArgs(chunk.args)];
      }
    } else {
      const streamingToolCall = message.toolCalls.find(
        (toolCall) => toolCall.argsChunks?.length,
      );
      if (streamingToolCall) {
        streamingToolCall.argsChunks!.push(convertToolChunkArgs(chunk.args));
      }
    }
  }
}

function mergeToolCallResultMessage(
  message: Message,
  event: ToolCallResultEvent,
) {
  const toolCall = message.toolCalls?.find(
    (toolCall) => toolCall.id === event.data.tool_call_id,
  );
  if (toolCall) {
    toolCall.result = event.data.content;
  }
}

function mergeInterruptMessage(message: Message, event: InterruptEvent) {
  message.isStreaming = false;
  message.options = event.data.options;
}
