// Spec 13.3 / 26.3: any string containing "(simulated)" renders with a small grey "simulated" tag.
export default function SimText({ text }) {
  if (!text || !text.includes('(simulated)')) return text || null
  return (
    <>
      {text.replace(/\s*\(simulated\)/g, '')}
      <span className="ml-1.5 whitespace-nowrap rounded bg-notsure-bg px-1.5 py-px align-middle text-[10px] font-medium uppercase tracking-wide text-notsure-fg">
        simulated
      </span>
    </>
  )
}
