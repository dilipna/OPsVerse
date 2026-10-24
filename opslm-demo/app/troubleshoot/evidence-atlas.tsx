export function EvidenceAtlas(){
  return <aside className="evidence-atlas" aria-label="Illustrated evidence pipeline">
    <div className="atlas-caption"><span>THE EVIDENCE ATLAS</span><span>FIG. 01</span></div>
    <svg viewBox="0 0 480 340" role="img" aria-labelledby="atlas-title" aria-describedby="atlas-description">
      <title id="atlas-title">A symptom becomes a traceable investigation</title>
      <desc id="atlas-description">Illustration: diagnostic input connects to pinned documentation and a reviewable brief. This is a workflow diagram, not live cluster telemetry.</desc>
      <defs><pattern id="atlas-grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="currentColor" strokeWidth=".5" opacity=".12"/></pattern></defs>
      <rect width="480" height="340" fill="url(#atlas-grid)"/>
      <g fill="none" stroke="currentColor" opacity=".16"><ellipse cx="240" cy="170" rx="160" ry="120"/><ellipse cx="240" cy="170" rx="120" ry="160" transform="rotate(48 240 170)"/><circle cx="240" cy="170" r="90"/><path d="M0 170H480M240 0V340" strokeDasharray="3 6"/></g>
      <path className="atlas-connection" d="M97 190C130 190 133 102 199 102S279 235 347 235" fill="none" strokeWidth="2" strokeDasharray="5 5"/>
      <g className="atlas-node"><rect x="33" y="157" width="128" height="66" rx="8"/><circle cx="51" cy="176" r="3"/><text x="64" y="180">01 / OBSERVE</text><text className="atlas-node-title" x="49" y="204">A failing Pod</text></g>
      <g className="atlas-node atlas-node-primary"><rect x="174" y="65" width="152" height="82" rx="8"/><path d="M194 83h14v19h-14zM198 88h6M198 92h6" fill="none"/><text x="218" y="94">02 / RETRIEVE</text><text className="atlas-node-title" x="194" y="125">Pinned evidence</text></g>
      <g className="atlas-node"><rect x="300" y="211" width="150" height="72" rx="8"/><text x="317" y="235">03 / REVIEW</text><text className="atlas-node-title" x="317" y="262">Your incident brief</text></g>
      <g className="atlas-coordinate"><text x="13" y="22">SOURCE → CONTEXT</text><text x="13" y="325">ILLUSTRATED WORKFLOW / NO CLUSTER CONNECTION</text></g>
      <g className="atlas-marker"><circle cx="97" cy="120" r="4"/><path d="M90 120h14M97 113v14"/><circle cx="360" cy="85" r="4"/><path d="M353 85h14M360 78v14"/></g>
    </svg>
    <div className="atlas-footer"><p><strong>Every conclusion needs a trail.</strong><br/>Start with a symptom. Keep the source in view.</p><span aria-hidden="true">↗</span></div>
  </aside>;
}
