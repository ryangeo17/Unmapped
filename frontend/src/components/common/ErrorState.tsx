interface Props {
  title: string
  message: string
  onRetry?: () => void
  children?: React.ReactNode
}

// A deliberate-looking failure: what happened, and what to do next.
export default function ErrorState({ title, message, onRetry, children }: Props) {
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-950">
      <p className="flex items-center gap-2 font-semibold">
        <span aria-hidden="true">⚠️</span>
        {title}
      </p>
      <p className="mt-1 text-sm">{message}</p>
      {children}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 min-h-11 rounded-lg bg-red-700 px-4 text-sm font-semibold text-white hover:bg-red-800"
        >
          Try again
        </button>
      )}
    </div>
  )
}
