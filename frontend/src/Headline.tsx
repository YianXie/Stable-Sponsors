import { formatPercent } from './format'
import type { Review } from './types'

function Share({ share, label }: { share: number; label: string }) {
  return (
    <div className="share">
      <p className="share-value">{formatPercent(share)}</p>
      <p className="share-label">{label}</p>
      <div className="meter" aria-hidden="true">
        <div className="meter-fill" style={{ width: `${share * 100}%` }} />
      </div>
    </div>
  )
}

export function Headline({ review }: { review: Review }) {
  return (
    <section aria-label="Headline" className="card headline">
      <h2 className="hero">
        <span className="hero-figure">
          {review.determined_match} / {review.teachers}
        </span>
        <span className="hero-label">teachers reproduced</span>
      </h2>
      <div className="shares">
        <Share share={review.share_of_all} label="of all teachers" />
        <Share share={review.share_of_determined} label="of determined teachers" />
      </div>
      <p className="plain">
        Reproduced means the rules give this teacher the same placement in every optimal solution,
        and it matches the office's.
      </p>
    </section>
  )
}
