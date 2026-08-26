<script lang="ts">
  import { onMount, tick } from 'svelte';

  export let selectedDocId: string | null = null;

  interface Message {
    role: 'user' | 'assistant';
    content: string;
    sources?: Source[];
    isStreaming?: boolean;
  }

  interface Source {
    document_id: string;
    document_name: string;
    content: string;
    score: number;
  }

  let messages: Message[] = [];
  let input = '';
  let isLoading = false;
  let abortController: AbortController | null = null;
  let chatEnd: HTMLElement | null = null;

  const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  function scrollToBottom() {
    chatEnd?.scrollIntoView({ behavior: 'smooth' });
  }

  onMount(() => {
    chatEnd = document.getElementById('chat-end');
  });

  async function sendMessage() {
    if (!input.trim() || isLoading || !selectedDocId) return;

    const userMessage = input.trim();
    input = '';
    isLoading = true;

    messages = [...messages, { role: 'user', content: userMessage }];
    messages = [...messages, { role: 'assistant', content: '', isStreaming: true }];

    await tick();
    scrollToBottom();

    abortController = new AbortController();

    try {
      const res = await fetch(`${apiUrl}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userMessage,
          document_id: selectedDocId
        }),
        signal: abortController.signal
      });

      if (!res.ok) throw new Error('Chat request failed');

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let fullContent = '';
      let sources: Source[] = [];

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') continue;

              try {
                const parsed = JSON.parse(data);
                if (parsed.content) {
                  fullContent += parsed.content;
                  messages = messages.map((m, i) =>
                    i === messages.length - 1 ? { ...m, content: fullContent } : m
                  );
                }
                if (parsed.sources) {
                  sources = parsed.sources;
                }
              } catch {}
            }
          }
          await tick();
          scrollToBottom();
        }
      }

      messages = messages.map((m, i) =>
        i === messages.length - 1
          ? { ...m, content: fullContent, isStreaming: false, sources }
          : m
      );
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        messages = messages.map((m, i) =>
          i === messages.length - 1
            ? { ...m, content: 'Error: Failed to get response', isStreaming: false }
            : m
        );
      }
    } finally {
      isLoading = false;
      abortController = null;
    }
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function clearChat() {
    messages = [];
  }

  function formatTime(date: Date = new Date()) {
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  }
</script>

<div class="flex-1 flex flex-col min-w-0">
  <header class="p-4 border-b border-slate-800 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-10">
    <div class="max-w-4xl mx-auto flex items-center justify-between">
      <div class="flex items-center gap-3">
        {#if selectedDocId}
          <div class="w-10 h-10 rounded-lg bg-indigo-900/30 flex items-center justify-center">
            <svg class="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div>
            <h1 class="font-semibold">Chat with Document</h1>
            <p class="text-xs text-slate-500">Selected document: {selectedDocId}</p>
          </div>
        {:else}
          <div class="w-10 h-10 rounded-lg bg-slate-800 flex items-center justify-center">
            <svg class="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <div>
            <h1 class="font-semibold">OmniDocAI Chat</h1>
            <p class="text-xs text-slate-500">Select a document to start chatting</p>
          </div>
        {/if}
      </div>

      {#if messages.length > 0}
        <button
          class="text-sm text-slate-400 hover:text-white px-3 py-1 rounded-lg hover:bg-slate-800 transition-colors"
          onclick={clearChat}
        >
          Clear Chat
        </button>
      {/if}
    </div>
  </header>

  <main class="flex-1 overflow-y-auto p-6 max-w-4xl mx-auto w-full">
    <div class="space-y-6">
      {#if messages.length === 0 && !selectedDocId}
        <div class="text-center py-12 text-slate-500">
          <svg class="w-16 h-16 mx-auto mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          <h2 class="text-xl font-medium mb-2">Welcome to OmniDocAI</h2>
          <p class="text-slate-400 max-w-md mx-auto">
            Upload a document from the sidebar, then ask questions about its content. I'll help you find answers, summarize, and analyze your documents.
          </p>
        </div>
      {:else if messages.length === 0 && selectedDocId}
        <div class="text-center py-12 text-slate-500">
          <svg class="w-16 h-16 mx-auto mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          <h2 class="text-xl font-medium mb-2">Ready to chat</h2>
          <p class="text-slate-400 max-w-md mx-auto">
            Ask me anything about your document. Try questions like "Summarize this document" or "What are the key points?"
          </p>
        </div>
      {/if}

      {#each messages as message, index (message)}
        <div class="flex gap-3 {message.role === 'user' ? 'flex-row-reverse' : ''}">
          <div
            class={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
              message.role === 'user'
                ? 'bg-indigo-500 text-white'
                : 'bg-slate-800 text-slate-400'
            }`}
          >
            {#if message.role === 'user'}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            {:else}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            {/if}
          </div>

          <div class={`flex-1 max-w-[85%] ${message.role === 'user' ? 'text-right' : ''}`}>
            <div
              class={`inline-block px-4 py-2 rounded-2xl text-sm ${
                message.role === 'user'
                  ? 'bg-indigo-500 text-white rounded-tr-sm'
                  : 'bg-slate-800 text-slate-100 rounded-tl-sm'
              }`}
            >
              {#if message.isStreaming}
                <span class="flex items-center gap-1">
                  {message.content}
                  <span class="animate-pulse">▌</span>
                </span>
              {:else}
                {message.content}
              {/if}
            </div>

            {#if message.sources && message.sources.length > 0}
              <details class="mt-2 text-xs text-slate-500">
                <summary class="cursor-pointer flex items-center gap-1 hover:text-slate-400">
                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Sources ({message.sources.length})
                </summary>
                <div class="mt-2 ml-4 space-y-1 border-l border-slate-700 pl-3">
                  {#each message.sources as source}
                    <div class="bg-slate-800/50 p-2 rounded">
                      <p class="font-medium text-slate-300">{source.document_name}</p>
                      <p class="truncate max-h-16 overflow-hidden">{source.content}</p>
                      <p class="text-xs text-slate-500 mt-1">Relevance: {(source.score * 100).toFixed(0)}%</p>
                    </div>
                  {/each}
                </div>
              </details>
            {/if}

            <p class="text-xs text-slate-500 mt-1">{formatTime()}</p>
          </div>
        </div>
      {/each}

      <div id="chat-end"></div>
    </div>
  </main>

  <footer class="p-4 border-t border-slate-800 bg-slate-900/50 backdrop-blur-sm">
    <div class="max-w-4xl mx-auto">
      <form onsubmit={(e) => { e.preventDefault(); sendMessage(); }} class="flex gap-2">
        <input
          type="text"
          bind:value={input}
          placeholder={selectedDocId ? "Ask about your document..." : "Select a document first"}
          disabled={isLoading || !selectedDocId}
          onkeydown={handleKeyDown}
          class="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        />
        <button
          type="submit"
          disabled={!input.trim() || isLoading || !selectedDocId}
          class="bg-indigo-500 hover:bg-indigo-400 disabled:bg-slate-700 disabled:cursor-not-allowed text-white px-6 py-3 rounded-xl font-medium transition-colors flex items-center gap-2"
        >
          {#if isLoading}
            <svg class="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          {:else}
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          {/if}
        </button>
      </form>
      <p class="text-xs text-slate-500 text-center mt-2">
        Press Enter to send, Shift+Enter for new line
      </p>
    </div>
  </footer>
</div>