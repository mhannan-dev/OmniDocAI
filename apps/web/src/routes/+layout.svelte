<script>
  import '../app.css';

  let { children } = $props();
</script>

<div class="min-h-full bg-slate-950 text-slate-100 flex">
  {@render children()}
</div>
