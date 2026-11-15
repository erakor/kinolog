import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ExternalRatings } from './ExternalRatings'

describe('ExternalRatings', () => {
  it('renders nothing without ratings', () => {
    const { container } = render(<ExternalRatings ratings={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('orders IMDb, Rotten Tomatoes, Metacritic regardless of payload order', () => {
    render(
      <ExternalRatings
        ratings={[
          { source: 'metacritic', score: 73, raw: '73/100', votes: null },
          { source: 'rotten_tomatoes', score: 83, raw: '83%', votes: null },
          { source: 'imdb', score: 87, raw: '8.7/10', votes: 10 },
        ]}
      />,
    )
    expect(screen.getByTestId('external-ratings')).toHaveTextContent('IMDb 8.7 · RT 83% · MC 73')
    expect(screen.getByLabelText('Rotten Tomatoes critics score 83%')).toBeInTheDocument()
  })
})
