<script lang="ts">
  import { onMount } from 'svelte';
  import Sidebar from '$lib/Sidebar.svelte';
  import ChatInterface from '$lib/ChatInterface.svelte';

  interface Document {
    id: string;
    name: string;
    size: number;
    type: string;
    uploadedAt: string;
    status: 'processing' | 'ready' | 'error';
  }

  let documents: Document[] = [];
  let selectedDocId: string | null = null;
  let isLoading = false;

  const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  let pollTimer: ReturnType<typeof setInterval> | null = null;

  async function fetchDocuments() {
    try {
      const res = await fetch(`${apiUrl}/documents`);
      if (res.ok) {
        const data = await res.json();
        documents = data.documents || [];
      }
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    }
    syncPolling();
  }

  // Indexing finishes asynchronously, so poll while anything is still processing.
  function syncPolling() {
    const busy = documents.some((d) => d.status === 'processing');
    if (busy && !pollTimer) {
      pollTimer = setInterval(fetchDocuments, 2000);
    } else if (!busy && pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function handleDocSelect(docId: string) {
    selectedDocId = docId;
  }

  onMount(() => {
    const onSelect = ((e: CustomEvent) => handleDocSelect(e.detail)) as EventListener;
    const onChanged = (() => fetchDocuments()) as EventListener;

    fetchDocuments();
    window.addEventListener('doc-select', onSelect);
    window.addEventListener('docs-changed', onChanged);

    return () => {
      window.removeEventListener('doc-select', onSelect);
      window.removeEventListener('docs-changed', onChanged);
      if (pollTimer) clearInterval(pollTimer);
    };
  });
</script>

<svelte:head>
  <title>OmniDocAI — Chat with your documents</title>
  <meta
    name="description"
    content="OmniDocAI turns your documents into a searchable, conversational knowledge base."
  />
</svelte:head>

<div class="flex h-screen">
  <Sidebar {documents} {selectedDocId} {isLoading} />

  <ChatInterface {selectedDocId} />
</div>
