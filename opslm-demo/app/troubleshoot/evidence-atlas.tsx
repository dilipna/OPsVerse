export function EvidenceAtlas(){
  return <aside className="evidence-workflow" aria-label="Illustrated evidence pipeline">
    <div className="workflow-caption"><span>THE INVESTIGATION WORKFLOW</span><span>HUMAN REVIEW</span></div>
    <div className="workflow-steps" role="img" aria-label="A symptom becomes a traceable investigation" aria-describedby="workflow-description">
      <div className="workflow-step"><span>01</span><div><strong>Capture a symptom</strong><p>Use sanitized diagnostic text.</p></div></div>
      <div className="workflow-step"><span>02</span><div><strong>Inspect the evidence</strong><p>Follow pinned official sources.</p></div></div>
      <div className="workflow-step"><span>03</span><div><strong>Keep a clear brief</strong><p>Review, annotate and export.</p></div></div>
    </div>
    <p id="workflow-description" className="workflow-footnote">Workflow illustration. No cluster connection or commands executed.</p>
  </aside>;
}
