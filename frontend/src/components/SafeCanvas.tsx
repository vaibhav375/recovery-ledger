import { Component, type ErrorInfo, type ReactNode } from "react";

/** Error boundary for decorative canvas content.
 *
 * Belt and braces alongside the `supportsWebGL()` pre-check: a GPU can also be
 * lost *after* a context is created (driver reset, tab backgrounded for a long
 * time, `WEBGL_lose_context`). Whatever the cause, the rule is the same —
 * ornament must never be able to take down the dashboard, so this renders
 * nothing at all on failure and lets the CSS gradient behind it stand in.
 */
export default class SafeCanvas extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Warn rather than throw: this is expected on machines without WebGL.
    console.warn("Decorative background disabled:", error.message, info.componentStack);
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}
