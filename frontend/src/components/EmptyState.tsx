import { empty } from './styles'

export function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className={empty}>
      <h3 className="mb-2 text-lg text-ink">{title}</h3>
      <p>{text}</p>
    </div>
  )
}
