<script lang="ts">
  import { onMount } from 'svelte';

  export let documents: Document[] = [];
  export let selectedDocId: string | null = null;
  export let isLoading = false;

  interface Document {
    id: string;
    name: string;
    size: number;
    type: string;
    uploadedAt: string;
    status: 'processing' | 'ready' | 'error';
  }

  interface UploadResponse {
    document: Document;
  }

  let dragActive = false;
  let uploadErrors: { name: string; reason: string }[] = [];
  let uploadProgress = 0;
  let showUpload = false;

  const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  async function handleFileUpload(files: FileList) {
    if (files.length === 0) return;
    uploadErrors = [];

    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch(`${apiUrl}/documents/upload`, {
          method: 'POST',
          body: formData
        });

        if (res.ok) {
          await res.json();
        } else {
          // A rejected upload used to fail silently: the dialog simply closed
          // and the file never appeared, with no clue why.
          const body = await res.json().catch(() => null);
          uploadErrors = [
            ...uploadErrors,
            { name: file.name, reason: body?.detail ?? `Upload failed (${res.status})` }
          ];
        }
      } catch (err) {
        console.error('Upload failed:', err);
        uploadErrors = [
          ...uploadErrors,
          { name: file.name, reason: 'Could not reach the server' }
        ];
      }
    }

    // Keep the dialog open when something went wrong, so the reason is readable.
    if (uploadErrors.length === 0) showUpload = false;
    // The page owns the document list; ask it to re-sync and start polling.
    window.dispatchEvent(new CustomEvent('docs-changed'));
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    dragActive = true;
  }

  function handleDragLeave(e: DragEvent) {
    e.preventDefault();
    dragActive = false;
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    dragActive = false;
    if (e.dataTransfer?.files) {
      handleFileUpload(e.dataTransfer.files);
    }
  }

  function selectDocument(doc: Document) {
    if (doc.status === 'ready') {
      selectedDocId = doc.id;
      window.dispatchEvent(new CustomEvent('doc-select', { detail: doc.id }));
    }
  }

  function formatSize(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatDate(dateStr: string) {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  function getStatusColor(status: Document['status']) {
    switch (status) {
      case 'ready': return 'text-green-400';
      case 'processing': return 'text-yellow-400 animate-pulse';
      case 'error': return 'text-red-400';
    }
  }

  async function deleteDocument(docId: string, e: Event) {
    e.stopPropagation();
    try {
      const res = await fetch(`${apiUrl}/documents/${docId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        documents = documents.filter(d => d.id !== docId);
        if (selectedDocId === docId) {
          selectedDocId = null;
          window.dispatchEvent(new CustomEvent('doc-select', { detail: null }));
        }
      }
    } catch (err) {
      console.error('Delete failed:', err);
    }
  }
</script>

<aside class="w-72 bg-slate-900 border-r border-slate-800 flex flex-col hidden lg:flex">
  <div class="p-4 border-b border-slate-800">
    <h2 class="text-lg font-semibold flex items-center gap-2">
      <svg class="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
      </svg>
      Documents
    </h2>
  </div>

  <div class="p-4 border-b border-slate-800">
    <button
      class="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-sm text-slate-300 transition-colors"
      onclick={() => showUpload = true}
    >
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
      </svg>
      Add Documents
    </button>
  </div>

  <div class="flex-1 overflow-y-auto p-4 space-y-2">
    {#if documents.length === 0}
      <div class="text-center py-12 text-slate-500">
        <svg class="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <p class="text-sm">No documents yet</p>
        <p class="text-xs mt-1">Click "Add Documents" to start</p>
      </div>
    {:else}
      {#each documents as doc (doc.id)}
        <div class="w-full">
          <div class="flex items-center gap-2">
            <button
              class={`flex-1 text-left p-3 rounded-lg transition-all flex items-center ${
                selectedDocId === doc.id
                  ? 'bg-indigo-900/30 border border-indigo-800'
                  : 'bg-slate-800 hover:bg-slate-700'
              }`}
              onclick={() => selectDocument(doc)}
              disabled={doc.status !== 'ready'}
            >
              <div class="flex items-start gap-3 flex-1 min-w-0">
                <div class="w-10 h-10 rounded-lg bg-slate-700 flex items-center justify-center flex-shrink-0">
                  {#if doc.type.startsWith('application/pdf')}
                    <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path fill="#fff" d="M14 2v6h6"/><text x="8" y="16" font-size="8" fill="#fff">PDF</text></svg>
                  {:else if doc.type.startsWith('text/')}
                    <svg class="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                  {:else}
                    <svg class="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/></svg>
                  {/if}
                </div>
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-medium truncate">{doc.name}</p>
                  <div class="flex items-center gap-2 mt-1 text-xs text-slate-500">
                    <span>{formatSize(doc.size)}</span>
                    <span>•</span>
                    <span>{formatDate(doc.uploadedAt)}</span>
                    <span class={getStatusColor(doc.status)}>{doc.status}</span>
                  </div>
                </div>
              </div>
            </button>
            <button
              class="flex-shrink-0 p-1.5 rounded hover:bg-red-900/30 text-slate-500 hover:text-red-400 transition-colors"
              onclick={(e) => deleteDocument(doc.id, e)}
              aria-label="Delete document"
              title="Delete"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>
      {/each}
    {/if}
  </div>

  <div class="p-4 border-t border-slate-800 text-xs text-slate-500 text-center">
    Powered by OmniDocAI
  </div>
</aside>

{#if showUpload}
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" role="dialog" aria-modal="true" aria-labelledby="upload-title">
    <button class="absolute inset-0" onclick={() => { showUpload = false; uploadErrors = []; }} aria-label="Close upload dialog"></button>
    <div class="bg-slate-900 rounded-xl p-6 w-full max-w-md mx-4 border border-slate-800 relative z-10">
      <div class="flex items-center justify-between mb-4">
        <h3 id="upload-title" class="text-lg font-semibold">Upload Documents</h3>
        <button class="text-slate-400 hover:text-white" onclick={() => { showUpload = false; uploadErrors = []; }} aria-label="Close">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>

      <div
        class={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          dragActive ? 'border-indigo-500 bg-indigo-900/20' : 'border-slate-700 hover:border-slate-600'
        }`}
        role="region"
        aria-label="File drop zone"
        ondragover={handleDragOver}
        ondragleave={handleDragLeave}
        ondrop={handleDrop}
      >
        <input
          type="file"
          multiple
          accept=".pdf,.txt,.md,.docx"
          class="hidden"
          id="file-input"
          onchange={(e) => handleFileUpload((e.target as HTMLInputElement).files!)}
        />
        <label for="file-input" class="cursor-pointer">
          <svg class="w-12 h-12 mx-auto text-slate-500 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          <p class="text-slate-300">Drag & drop files here</p>
          <p class="text-sm text-slate-500 mt-1">or click to browse</p>
          <p class="text-xs text-slate-600 mt-2">PDF, TXT, MD, DOCX (max 10MB each)</p>
        </label>
      </div>

      {#if uploadErrors.length > 0}
        <ul class="mt-4 space-y-1 rounded-lg border border-red-900/60 bg-red-950/40 p-3">
          {#each uploadErrors as failure}
            <li class="text-sm text-red-300">
              <span class="font-medium">{failure.name}</span>
              <span class="text-red-400/80"> — {failure.reason}</span>
            </li>
          {/each}
        </ul>
      {/if}

      <div class="mt-4 flex justify-end gap-2">
        <button class="px-4 py-2 text-sm text-slate-300 hover:text-white" onclick={() => { showUpload = false; uploadErrors = []; }}>
          Cancel
        </button>
      </div>
    </div>
  </div>
{/if}