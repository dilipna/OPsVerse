export function EvidenceAtlas(){
  return <aside className="evidence-atlas signal-board" aria-label="Illustrated evidence pipeline">
    <div className="atlas-caption"><span>SIGNAL PATH / 001</span><span>SCHEMATIC</span></div>
    <div className="signal-diagram" role="img" aria-label="A symptom becomes a traceable investigation" aria-describedby="signal-description">
      <div className="signal-guide" aria-hidden="true"><i/><i/><i/><i/><i/></div>
      <div className="signal-card signal-input"><span className="signal-index">01</span><div><span className="signal-kicker">CAPTURE THE SIGNAL</span><strong>Something isn't right.</strong><code>ImagePullBackOff</code></div><span className="signal-glyph" aria-hidden="true">↗</span></div>
      <div className="signal-connector" aria-hidden="true"><span>↓</span><b>TRACE IT TO THE SOURCE</b></div>
      <div className="signal-card signal-source"><span className="signal-index">02</span><div><span className="signal-kicker">PINNED DOCUMENTATION</span><strong>Find what supports it.</strong><span className="signal-source-line"><i/><i/><i/></span></div><span className="signal-glyph" aria-hidden="true">⌕</span></div>
      <div className="signal-connector" aria-hidden="true"><span>↓</span><b>KEEP WHAT YOU CAN VERIFY</b></div>
      <div className="signal-card signal-brief"><span className="signal-index">03</span><div><span className="signal-kicker">HUMAN REVIEW</span><strong>Leave a useful trail.</strong><span className="signal-tags"><span>Evidence</span><span>Gaps</span><span>Notes</span></span></div><span className="signal-glyph" aria-hidden="true">↳</span></div>
    </div>
    <p id="signal-description" className="signal-description">Illustrated workflow using an example status. No live cluster connection.</p>
  </aside>;
}
