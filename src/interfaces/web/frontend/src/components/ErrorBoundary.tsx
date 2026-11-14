import { Component, type ReactNode } from 'react'
import { empty } from './ui'

interface State {
  error: Error | null
}

/** Shows a load failure (data or code-split chunk) in place of the view. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, State> {
  state: State = { error: null }

  componentDidUpdate(prev: { resetKey?: string }) {
    // A refresh or navigation retries a view that failed to load.
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null })
  }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  render() {
    if (this.state.error) {
      return <p className={empty}>Could not load this view: {this.state.error.message}</p>
    }
    return this.props.children
  }
}
