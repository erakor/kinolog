import { empty } from './styles'

export function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className={empty}>
      <h3 className="text-ink mb-2 text-lg">{title}</h3>
      <p>{text}</p>
    </div>
  )
}
