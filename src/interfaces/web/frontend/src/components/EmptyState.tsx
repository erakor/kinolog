import { empty } from './ui'

export function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className={empty}>
      <h3 className="text-ink mb-2 text-[1.17em]">{title}</h3>
      <p>{text}</p>
    </div>
  )
}
