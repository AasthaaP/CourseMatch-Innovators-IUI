// Spec 28.2: the question, the two options as buttons, and a dismiss control. Shown in the chat panel.
export default function Clarification({ clarification, onAnswer, onDismiss }) {
  return (
    <div className="rounded border border-line bg-notsure-bg p-3 text-sm">
      <p>{clarification.question}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {clarification.options.map((o) => (
          <button key={o.id} type="button" onClick={() => onAnswer(o)} className="rounded border border-line bg-white px-2 py-1 hover:border-accent">
            {o.label}
          </button>
        ))}
        <button type="button" onClick={onDismiss} className="px-2 py-1 text-muted underline">Dismiss</button>
      </div>
    </div>
  )
}
