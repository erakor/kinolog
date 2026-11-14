import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { Modal } from './Modal'

function Harness() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button onClick={() => setOpen(true)}>open</button>
      {open && (
        <Modal title="Hello" onClose={() => setOpen(false)}>
          <input aria-label="first" />
          <button>second</button>
        </Modal>
      )}
    </>
  )
}

describe('Modal', () => {
  it('has dialog semantics and focuses the first field', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByText('open'))
    const dialog = screen.getByRole('dialog', { name: 'Hello' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByLabelText('first')).toHaveFocus()
  })

  it('closes on Escape and restores focus to the opener', async () => {
    render(<Harness />)
    const opener = screen.getByText('open')
    await userEvent.click(opener)
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(opener).toHaveFocus()
  })

  it('closes on the close button and on backdrop click, not on dialog click', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByText('open'))
    await userEvent.click(screen.getByRole('dialog'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText('Close'))
    expect(screen.queryByRole('dialog')).toBeNull()

    await userEvent.click(screen.getByText('open'))
    await userEvent.click(screen.getByTestId('modal-backdrop'))
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
