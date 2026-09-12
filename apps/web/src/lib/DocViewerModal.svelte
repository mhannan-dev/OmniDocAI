<script lang="ts">
  import { onMount, tick } from 'svelte';

  export let isOpen = false;
  export let documentId: string | null = null;
  export let documentName: string = '';
  export let highlightText: string = '';
  export let score: number = 0;
  export let onClose: () => void;

  const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  let fullContent = '';
  let isLoading = false;
  let error: string | null = null;
  let docMeta: any = null;

  $: if (isOpen && documentId) {
    loadDocument(documentId);
  }

  async function loadDocument(id: string) {
    isLoading = true;
    error = null;
    fullContent = '';
    docMeta = null;

    try {
      const res = await fetch(`${apiUrl}/documents/${id}/content`);
      if (!res.ok) throw new Error(`Failed to load document (${res.status})`);
      const data = await res.json();
      docMeta = data.document;
      fullContent = data.content || '';
      await tick();
      scrollToHighlight();
    } catch (err: any) {
      error = err.message || 'Failed to load document content';
    } finally {
      isLoading = false;
    }
  }

  function scrollToHighlight() {
    setTimeout(() => {
      const el = document.getElementById('citation-highlight');
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 100);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape' && isOpen) {
      onClose();
    }
  }

  // Find and split document text to place highlight on cited text
  function getSegments(text: string, querySnippet: string) {
    if (!querySnippet || !text) {
      return { before: text, match: '', after: '' };
    }

    const cleanSnippet = querySnippet.trim();
    // Try matching full snippet first
    let idx = text.indexOf(cleanSnippet);

    // If not found (e.g. whitespace differences), try a shorter sub-slice (first 100 chars)
    if (idx === -1 && cleanSnippet.length > 50) {
      const sub = cleanSnippet.slice(0, 80).trim();
      idx = text.indexOf(sub);
      if (idx !== -1) {
        return {
          before: text.slice(0, idx),
          match: text.slice(idx, idx + sub.length),
          after: text.slice(idx + sub.length)
        };
      }
    }

    if (idx === -1) {
      return { before: text, match: '', after: '' };
    }

    return {
      before: text.slice(0, idx),
      match: text.slice(idx, idx + cleanSnippet.length),
      after: text.slice(idx + cleanSnippet.length)
    };
  }

  $: segments = getSegments(fullContent, highlightText);
</script>

<svelte:window onkeydown={handleKeydown} />

{#if isOpen}
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
    <div
      class="relative w-full max-w-4xl max-h-[88vh] flex flex-col bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl overflow-hidden"
    >
      <!-- Header -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90 sticky top-0 z-10">
        <div class="flex items-center gap-3 min-w-0">
          <div class="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center flex-shrink-0">
            <svg class="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h2 class="text-base font-semibold text-slate-100 truncate">{documentName || 'Document Viewer'}</h2>
              {#if score > 0}
                <span class="px-2 py-0.5 text-xs font-medium rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  {(score * 100).toFixed(0)}% Match
                </span>
              {/if}
            </div>
            <p class="text-xs text-slate-500">
              {#if docMeta}
                {(docMeta.size / 1024).toFixed(1)} KB &bull; {docMeta.chunks} chunks &bull; Highlighted cited passage below
              {:else}
                Cited passage in context
              {/if}
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2">
          {#if documentId}
            <a
              href={`${apiUrl}/documents/${documentId}/file`}
              download={documentName}
              target="_blank"
              rel="noopener noreferrer"
              class="px-3 py-1.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors border border-slate-700 flex items-center gap-1.5 cursor-pointer"
              title="Download original file"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Download
            </a>
          {/if}

          <button
            onclick={onClose}
            class="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
            aria-label="Close modal"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Content Area -->
      <div class="flex-1 overflow-y-auto p-6 text-sm text-slate-300 font-mono leading-relaxed bg-slate-950/60">
        {#if isLoading}
          <div class="py-24 text-center text-slate-500 flex flex-col items-center gap-3">
            <svg class="w-8 h-8 animate-spin text-indigo-400" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <p>Loading document text and locating cited passage...</p>
          </div>
        {:else if error}
          <div class="py-16 text-center text-rose-400">
            <p class="font-medium">{error}</p>
          </div>
        {:else if fullContent}
          <div class="whitespace-pre-wrap font-sans text-slate-200">
            <span>{segments.before}</span>{#if segments.match}<mark
                id="citation-highlight"
                class="bg-amber-500/25 text-amber-100 border border-amber-500/60 rounded px-1.5 py-0.5 font-medium shadow-sm ring-2 ring-amber-400/30 transition-all duration-300"
              >{segments.match}</mark>{/if}<span>{segments.after}</span>
          </div>
        {:else}
          <div class="py-16 text-center text-slate-500">
            <p>No text content available in this document.</p>
          </div>
        {/if}
      </div>

      <!-- Footer Info -->
      <div class="px-6 py-3 border-t border-slate-800 bg-slate-900/90 text-xs text-slate-500 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="inline-block w-2.5 h-2.5 rounded-full bg-amber-400"></span>
          <span>Cited snippet highlighted in yellow</span>
        </div>
        <span>Press <kbd class="px-1.5 py-0.5 bg-slate-800 border border-slate-700 rounded text-slate-400 font-mono">ESC</kbd> to close</span>
      </div>
    </div>
  </div>
{/if}
