import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ExternalRatings } from './ExternalRatings'

describe('ExternalRatings', () => {
  it('renders nothing without ratings', () => {
    const { container } = render(<ExternalRatings ratings={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the scores in payload order with provider-text tooltips', () => {
    render(
      <ExternalRatings
        ratings={[
          { source: 'imdb', score: 87, raw: '8.7/10', votes: 10 },
          { source: 'rotten_tomatoes', score: 83, raw: '83%', votes: null },
          { source: 'metacritic', score: 73, raw: '73/100', votes: null },
        ]}
      />,
    )
    expect(screen.getByTestId('external-ratings')).toHaveTextContent('IMDb 8.7 · RT 83% · MC 73')
    expect(screen.getByLabelText('Rotten Tomatoes 83%')).toBeInTheDocument()
  })
})
