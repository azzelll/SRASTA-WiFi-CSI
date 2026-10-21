// Realtime bursts and polling share one request; a queued refresh runs after it.
export function coalesceRefresh(refresh: () => Promise<void>) {
  let running = false, queued = false, closed = false;
  return {
    async request() {
      if (closed) return;
      if (running) { queued = true; return; }
      running = true;
      try {
        do { queued = false; await refresh(); } while (queued && !closed);
      } finally { running = false; }
    },
    close() { closed = true; queued = false; },
  };
}
