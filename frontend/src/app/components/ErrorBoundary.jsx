// Catches a screen that crashes while rendering, so one broken page never blanks the whole app.
//
// Also handles the most common real-world crash after a deploy: a member's open tab asks for a code chunk of the old
// build that no longer exists ("Loading chunk 12 failed"). We reload once to fetch the new build; if that already
// happened in the last minute, we show the message instead of looping.
import { Component } from "react";
import { Button, Card } from "./ui";

const RELOAD_KEY = "ch-chunk-reload-at";

function isChunkError(error) {
  const s = `${error?.name || ""} ${error?.message || ""}`;
  return /ChunkLoadError|Loading chunk [\w-]+ failed|Loading CSS chunk|dynamically imported module/i.test(s);
}

function reloadedRecently() {
  try { return Date.now() - Number(sessionStorage.getItem(RELOAD_KEY) || 0) < 60_000; } catch { return true; }
}

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    if (isChunkError(error) && !reloadedRecently()) {
      try { sessionStorage.setItem(RELOAD_KEY, String(Date.now())); } catch { /* private mode */ }
      window.location.reload();
      return;
    }
    // eslint-disable-next-line no-console
    console.error("Screen crashed", error, info?.componentStack);
  }

  componentDidUpdate(prev) {
    // Moving to another page clears the error, so the menu still works after one screen fails.
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    const chunk = isChunkError(this.state.error);
    return (
      <div className="min-h-[40vh] grid place-items-center px-4" role="alert">
        <Card className="max-w-md w-full space-y-3 text-center">
          <p className="text-lg font-semibold text-bz-ink">
            {chunk ? "A new version of the app is ready." : "This screen didn't load."}
          </p>
          <p className="text-bz-muted">
            {chunk ? "Reload to get it. Nothing you saved is lost." : "Try again. If it keeps happening, write to the team from Support."}
          </p>
          <div className="flex justify-center gap-2">
            <Button variant="primary" onClick={() => window.location.reload()} data-testid="error-reload">Reload</Button>
            {!chunk && <Button variant="secondary" onClick={() => this.setState({ error: null })}>Try again</Button>}
          </div>
        </Card>
      </div>
    );
  }
}
