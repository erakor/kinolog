import { useId } from 'react'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { fieldCheck } from './styles'

interface CheckFieldProps {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}

/** Checkbox with its label, as used in the log and edit dialogs. */
export function CheckField({ label, checked, onChange }: CheckFieldProps) {
  const id = useId()
  return (
    <div className={fieldCheck}>
      <Checkbox id={id} checked={checked} onCheckedChange={(v) => onChange(v === true)} />
      <Label htmlFor={id}>{label}</Label>
    </div>
  )
}
