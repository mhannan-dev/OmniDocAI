<script lang="ts">
  import { onMount, tick } from 'svelte';
  import DocViewerModal from '$lib/DocViewerModal.svelte';

  export let selectedDocId: string | null = null;

  interface Message {
    role: 'user' | 'assistant';
    content: string;
    sources?: Source[];
    isStreaming?: boolean;
    created_at?: string;
  }

  interface Source {
    document_id: string;
    document_name: string;
    content: string;
    raw_content?: string;
    score: number;
    chunk_id?: string;
  }

  interface TokenUsage {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    prompt_cache_hit_tokens?: number;
    prompt_cache_miss_tokens?: number;
  }

  let messages: Message[] = [];
  let input = '';
  let isLoading = false;
  let abortController: AbortController | null = null;
  let chatEnd: HTMLElement | null = null;

  let currentDocId: string | null = null;
  let currentConversationId: string | null = null;
  let latestUsage: TokenUsage | null = null;

  let docSummary: string | null = null;
  let suggestedQuestions: string[] = [];
  let isSummaryLoading = false;

  let isDocModalOpen = false;
  let modalDocId: string | null = null;
  let modalDocName = '';
  let modalHighlightText = '';
  let modalScore = 0;

  function openDocViewer(source: Source) {
    modalDocId = source.document_id;
    modalDocName = source.document_name;
    modalHighlightText = source.raw_content || source.content;
    modalScore = source.score || 0;
    isDocModalOpen = true;
  }

  function closeDocViewer() {
    isDocModalOpen = false;
  }

  const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  function scrollToBottom() {
    chatEnd?.scrollIntoView({ behavior: 'smooth' });
  }

  onMount(() => {
    chatEnd = document.getElementById('chat-end');
  });

  $: if (selectedDocId !== currentDocId) {
    currentDocId = selectedDocId;
    loadDocumentChat(selectedDocId);
  }

  async function fetchSummary(docId: string) {
    isSummaryLoading = true;
    try {
      const res = await fetch(`${apiUrl}/documents/${docId}/summary`);
      if (res.ok) {
        const data = await res.json();
        docSummary = data.summary || null;
        suggestedQuestions = data.questions || [];
      }
    } catch (err) {
      console.error('Failed to load document summary:', err);
    } finally {
      isSummaryLoading = false;
    }
  }

  async function loadDocumentChat(docId: string | null) {
    messages = [];
    currentConversationId = null;
    latestUsage = null;
    docSummary = null;
    suggestedQuestions = [];
    if (!docId) return;

    fetchSummary(docId);

    try {
      const res = await fetch(`${apiUrl}/documents/${docId}/conversations`);
      if (res.ok) {
        const data = await res.json();
        const convs = data.conversations || [];
        if (convs.length > 0) {
          const activeConv = convs[0];
          currentConversationId = activeConv.id;
          await loadConversationHistory(activeConv.id);
        }
      }
    } catch (err) {
      console.error('Failed to load conversation history:', err);
    }
  }

  async function loadConversationHistory(convId: string) {
    try {
      const res = await fetch(`${apiUrl}/conversations/${convId}`);
      if (res.ok) {
        const data = await res.json();
        messages = (data.messages || []).map((m: any) => ({
          role: m.role,
          content: m.content,
          sources: m.sources,
          isStreaming: false,
          created_at: m.created_at
        }));
        await tick();
        scrollToBottom();
      }
    } catch (err) {
      console.error('Failed to fetch conversation messages:', err);
    }
  }

  function startNewChat() {
    messages = [];
    currentConversationId = null;
    latestUsage = null;
  }

  function askQuestion(q: string) {
    input = q;
    sendMessage();
  }

  async function sendMessage() {
    if (!input.trim() || isLoading || !selectedDocId) return;

    const userMessage = input.trim();
    input = '';
    isLoading = true;

    messages = [...messages, { role: 'user', content: userMessage, created_at: new Date().toISOString() }];
    messages = [...messages, { role: 'assistant', content: '', isStreaming: true, created_at: new Date().toISOString() }];

    await tick();
    scrollToBottom();

    abortController = new AbortController();

    try {
      const res = await fetch(`${apiUrl}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userMessage,
          document_id: selectedDocId,
          conversation_id: currentConversationId
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
                if (parsed.conversation_id) {
                  currentConversationId = parsed.conversation_id;
                }
                if (parsed.content) {
                  fullContent += parsed.content;
                  messages = messages.map((m, i) =>
                    i === messages.length - 1 ? { ...m, content: fullContent } : m
                  );
                }
                if (parsed.sources) {
                  sources = parsed.sources;
                }
                if (parsed.usage) {
                  latestUsage = parsed.usage;
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

  async function clearChat() {
    if (currentConversationId) {
      try {
        await fetch(`${apiUrl}/conversations/${currentConversationId}`, { method: 'DELETE' });
      } catch (e) {
        console.error('Failed to delete conversation:', e);
      }
    }
    messages = [];
    currentConversationId = null;
    latestUsage = null;
  }

  function formatTime(dateStr?: string) {
    const d = dateStr ? new Date(dateStr) : new Date();
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  }
</script>

<div class="flex-1 flex flex-col min-w-0">
  <header class="p-4 border-b border-slate-800 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-10">
    <div class="max-w-4xl mx-auto flex items-center justify-between">
      <div class="flex items-center gap-3">
        {#if selectedDocId === '__all__'}
          <div class="w-10 h-10 rounded-lg bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center">
            <svg class="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h1 class="font-semibold">Chat with All Documents</h1>
              <span class="text-[10px] bg-indigo-950 text-indigo-300 px-2 py-0.5 rounded border border-indigo-700/60 font-medium">
                🌐 Workspace Search
              </span>
              {#if latestUsage}
                <span class="text-[10px] bg-slate-800 text-indigo-300 px-2 py-0.5 rounded border border-slate-700 font-mono">
                  ⚡ {latestUsage.total_tokens ?? 0} tok
                </span>
              {/if}
            </div>
            <p class="text-xs text-slate-400">Searching, synthesizing, and comparing across all files</p>
          </div>
        {:else if selectedDocId}
          <div class="w-10 h-10 rounded-lg bg-indigo-900/30 flex items-center justify-center">
            <svg class="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h1 class="font-semibold">Chat with Document</h1>
              {#if latestUsage}
                <span class="text-[10px] bg-slate-800 text-indigo-300 px-2 py-0.5 rounded border border-slate-700 font-mono">
                  ⚡ {latestUsage.total_tokens ?? 0} tok
                  {#if latestUsage.prompt_cache_hit_tokens}
                    ({latestUsage.prompt_cache_hit_tokens} cached)
                  {/if}
                </span>
              {/if}
            </div>
            <p class="text-xs text-slate-500 truncate max-w-sm">Selected: {selectedDocId}</p>
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

      {#if selectedDocId}
        <div class="flex items-center gap-2">
          <button
            class="text-xs text-indigo-300 hover:text-white px-2.5 py-1.5 rounded-lg bg-indigo-950/60 hover:bg-indigo-900/80 border border-indigo-800/50 transition-colors flex items-center gap-1.5 cursor-pointer"
            onclick={startNewChat}
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            New Chat
          </button>
          {#if messages.length > 0}
            <button
              class="text-xs text-slate-400 hover:text-rose-400 px-2.5 py-1.5 rounded-lg hover:bg-slate-800 transition-colors cursor-pointer"
              onclick={clearChat}
              title="Delete this conversation"
            >
              Clear
            </button>
          {/if}
        </div>
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
        {#if isSummaryLoading}
          <div class="space-y-4 py-4 animate-pulse">
            <div class="p-5 rounded-2xl bg-slate-800/40 border border-slate-700/50 space-y-3">
              <div class="h-4 bg-indigo-500/20 rounded w-1/4"></div>
              <div class="h-3 bg-slate-700/60 rounded w-full"></div>
              <div class="h-3 bg-slate-700/60 rounded w-5/6"></div>
            </div>
            <div class="space-y-2">
              <div class="h-3 bg-slate-700/40 rounded w-1/3"></div>
              <div class="h-12 bg-slate-800/40 rounded-xl"></div>
              <div class="h-12 bg-slate-800/40 rounded-xl"></div>
              <div class="h-12 bg-slate-800/40 rounded-xl"></div>
            </div>
          </div>
        {:else if docSummary}
          <div class="space-y-5 py-2">
            <!-- Executive Summary Card -->
            <div class="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-950/40 via-slate-900 to-slate-900/90 border border-indigo-500/30 p-5 shadow-lg backdrop-blur-sm">
              <div class="absolute -top-12 -right-12 w-32 h-32 bg-indigo-500/10 rounded-full blur-2xl pointer-events-none"></div>
              <div class="flex items-center gap-2 mb-2.5">
                <span class="flex h-2 w-2 relative">
                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                  <span class="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
                </span>
                <h3 class="text-xs font-semibold uppercase tracking-wider text-indigo-400 flex items-center gap-1.5">
                  <svg class="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Document Executive Summary
                </h3>
              </div>
              <p class="text-slate-200 text-sm leading-relaxed">
                {docSummary}
              </p>
            </div>

            <!-- Suggested Questions -->
            {#if suggestedQuestions && suggestedQuestions.length > 0}
              <div class="space-y-2.5">
                <div class="flex items-center justify-between">
                  <p class="text-xs font-medium text-slate-400 flex items-center gap-1.5">
                    <svg class="w-3.5 h-3.5 text-amber-400" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14H8a4 4 0 01-.82-7.915A4 4 0 0116 10a3.993 3.993 0 01-4 4z" />
                    </svg>
                    Suggested Questions (Click to Ask)
                  </p>
                  <span class="text-[10px] text-slate-500">Instant query</span>
                </div>
                <div class="grid grid-cols-1 gap-2">
                  {#each suggestedQuestions as question}
                    <button
                      type="button"
                      class="group w-full text-left p-3.5 rounded-xl bg-slate-800/80 hover:bg-indigo-950/40 border border-slate-700/80 hover:border-indigo-500/50 transition-all flex items-center justify-between gap-3 text-slate-200 hover:text-white cursor-pointer shadow-sm hover:shadow-indigo-500/5"
                      onclick={() => askQuestion(question)}
                    >
                      <span class="text-sm font-medium leading-snug group-hover:text-indigo-200 transition-colors flex items-center gap-2.5">
                        <span class="w-1.5 h-1.5 rounded-full bg-indigo-400 group-hover:scale-125 transition-transform flex-shrink-0"></span>
                        {question}
                      </span>
                      <svg class="w-4 h-4 text-slate-500 group-hover:text-indigo-400 group-hover:translate-x-0.5 transition-all flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                      </svg>
                    </button>
                  {/each}
                </div>
              </div>
            {/if}
          </div>
        {:else}
          <div class="text-center py-12 text-slate-500">
            <svg class="w-16 h-16 mx-auto mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <h2 class="text-xl font-medium mb-2">Ready to chat</h2>
            <p class="text-slate-400 max-w-md mx-auto mb-4">
              Ask me anything about your document. Try one of these questions:
            </p>
            <div class="flex flex-wrap justify-center gap-2 max-w-lg mx-auto">
              <button
                type="button"
                class="text-xs bg-slate-800 hover:bg-slate-700 text-indigo-300 border border-slate-700 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
                onclick={() => askQuestion("What are the key points in this document?")}
              >
                What are the key points in this document?
              </button>
              <button
                type="button"
                class="text-xs bg-slate-800 hover:bg-slate-700 text-indigo-300 border border-slate-700 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
                onclick={() => askQuestion("Can you summarize this document?")}
              >
                Can you summarize this document?
              </button>
            </div>
          </div>
        {/if}
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
              <details class="mt-2 text-xs text-slate-500" open>
                <summary class="cursor-pointer flex items-center gap-1.5 hover:text-slate-400 select-none">
                  <svg class="w-3.5 h-3.5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span class="font-medium text-slate-400">Sources ({message.sources.length}) &bull; Click to highlight in document</span>
                </summary>
                <div class="mt-2 ml-4 space-y-2 border-l border-slate-700 pl-3">
                  {#each message.sources as source}
                    <button
                      type="button"
                      class="w-full text-left bg-slate-800/60 hover:bg-slate-800 p-2.5 rounded-lg border border-slate-700/60 hover:border-indigo-500/50 transition-all cursor-pointer group"
                      onclick={() => openDocViewer(source)}
                    >
                      <div class="flex items-center justify-between gap-2 mb-1">
                        <p class="font-medium text-slate-200 group-hover:text-indigo-300 transition-colors flex items-center gap-1.5 truncate">
                          <svg class="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                          <span class="truncate">{source.document_name}</span>
                        </p>
                        <span class="text-[10px] bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 px-1.5 py-0.5 rounded font-mono flex-shrink-0">
                          {(source.score * 100).toFixed(0)}% match
                        </span>
                      </div>
                      <p class="text-slate-400 text-xs line-clamp-2 leading-relaxed group-hover:text-slate-300 transition-colors">{source.content}</p>
                      <div class="mt-1.5 flex items-center text-[11px] text-indigo-400/80 group-hover:text-indigo-300 transition-colors">
                        <span>View in document with highlight &rarr;</span>
                      </div>
                    </button>
                  {/each}
                </div>
              </details>
            {/if}

            <p class="text-xs text-slate-500 mt-1">{formatTime(message.created_at)}</p>
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
          placeholder={selectedDocId === '__all__' ? "Ask a question across all documents..." : selectedDocId ? "Ask about your document..." : "Select a document first"}
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

  <DocViewerModal
    isOpen={isDocModalOpen}
    documentId={modalDocId}
    documentName={modalDocName}
    highlightText={modalHighlightText}
    score={modalScore}
    onClose={closeDocViewer}
  />
</div>