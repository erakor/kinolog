import { render, screen, waitFor } from '@testing-library/react'
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
  it('focuses the first field, not the close button, when the dialog has only buttons', async () => {
    render(
      <Modal title="Buttons" onClose={() => {}}>
        <button>only</button>
      </Modal>,
    )
    expect(screen.getByText('only')).toHaveFocus()
  })

  it('has dialog semantics and focuses the first field', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByText('open'))
    const dialog = screen.getByRole('dialog', { name: 'Hello' })
    expect(dialog).toBeInTheDocument()
    // Radix marks the rest of the page aria-hidden instead of using aria-modal.
    expect(screen.getByText('open')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'open' })).toBeNull()
    expect(screen.getByLabelText('first')).toHaveFocus()
  })

  it('closes on Escape and restores focus to the opener', async () => {
    render(<Harness />)
    const opener = screen.getByText('open')
    await userEvent.click(opener)
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
    // Radix restores focus in a timeout after unmount.
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('closes on the close button and on backdrop click, not on dialog click', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByText('open'))
    await userEvent.click(screen.getByRole('dialog'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText('Close'))
    expect(screen.queryByRole('dialog')).toBeNull()

    await userEvent.click(screen.getByText('open'))
    await userEvent.click(document.querySelector<HTMLElement>('[data-slot="dialog-overlay"]')!)
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
