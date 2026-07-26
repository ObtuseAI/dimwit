export const meta = {
  name: 'wanefall-char-review',
  description: 'Adversarial vision-review of 8 generated WANEFALL characters vs their concept art',
  phases: [
    { title: 'Review', detail: 'one vision agent per character: render vs concept' },
    { title: 'Verify', detail: 'skeptic re-checks every PASS and every REDO call' },
  ],
}

// Each character: concept front crop + the clean (no-glow) textured renders + clay geometry proof.
const RAIN = 'C:/Users/developer/Documents/Dimwit'
const CHARS = [
  ['01_vorlax','blue armor, cyan energy seams'],
  ['02_ekris','silver/white plated armor'],
  ['03_zythan','purple armor, magenta seams'],
  ['04_qorin','green/mossy organic armor'],
  ['05_therak','orange/red molten armor'],
  ['06_ullio','teal/cyan glowing armor'],
  ['07_kelous','black + gold trimmed armor'],
  ['08_nexor','pink/white sleek armor'],
]

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['character','shapeMatch','colorMatch','seamDetail','headFace','glowPresent','overall','issues','redo'],
  properties: {
    character:  { type: 'string' },
    shapeMatch: { type: 'integer', minimum: 0, maximum: 10, description: 'silhouette/proportions vs concept' },
    colorMatch: { type: 'integer', minimum: 0, maximum: 10, description: 'palette/material vs concept' },
    seamDetail: { type: 'integer', minimum: 0, maximum: 10, description: 'armor seams/panel definition present & crisp' },
    headFace:   { type: 'integer', minimum: 0, maximum: 10, description: 'head present, face structure readable, not a blob' },
    glowPresent:{ type: 'boolean', description: 'TRUE if any emission/glow/bloom is visible (user wants NONE)' },
    overall:    { type: 'integer', minimum: 0, maximum: 10 },
    issues:     { type: 'array', items: { type: 'string' } },
    redo:       { type: 'boolean', description: 'true if this character should be re-processed' },
    redoReason: { type: 'string' },
  },
}

const VERIFY_SCHEMA = {
  type: 'object',
  required: ['character','agree','correctedOverall','correctedRedo','note'],
  properties: {
    character:        { type: 'string' },
    agree:            { type: 'boolean', description: 'do you agree with the first reviewer?' },
    correctedOverall: { type: 'integer', minimum: 0, maximum: 10 },
    correctedRedo:    { type: 'boolean' },
    note:             { type: 'string' },
  },
}

const results = await pipeline(
  CHARS,
  ([name, desc]) => agent(
    `You are a hard-nosed game-art director reviewing an auto-generated 3D character against its concept art.\n` +
    `Character: ${name} (concept: ${desc}).\n\n` +
    `Look at these images with the Read tool:\n` +
    `  CONCEPT (ground truth): ${RAIN}/artifacts/fronts/${name}.png\n` +
    `  GENERATED textured front:        ${RAIN}/artifacts/${name}_textured/mview_front.png\n` +
    `  GENERATED textured three-quarter:${RAIN}/artifacts/${name}_textured/mview_threequarter.png\n` +
    `  GENERATED clay geometry (front): ${RAIN}/artifacts/${name}_clay/mview_front.png\n\n` +
    `Score honestly 0-10 on: shape/proportions, color/palette match, armor seam/panel definition, head+face readability.\n` +
    `CRITICAL: the user explicitly wants NO glow/emission/bloom — set glowPresent=true if you see ANY.\n` +
    `Set redo=true if overall < 6, or if the head is a blob, or if glow is present.\n` +
    `If a generated image is missing/blank, score 0 and redo=true. Return the structured verdict.`,
    { label: `review:${name}`, phase: 'Review', schema: REVIEW_SCHEMA }
  ),
  (rev, [name, desc]) => agent(
    `Skeptically re-check another reviewer's verdict on auto-generated character ${name} (concept: ${desc}).\n` +
    `Their verdict: ${JSON.stringify(rev)}\n\n` +
    `Independently look at:\n` +
    `  CONCEPT: ${RAIN}/artifacts/fronts/${name}.png\n` +
    `  GENERATED: ${RAIN}/artifacts/${name}_textured/mview_front.png and ${RAIN}/artifacts/${name}_textured/mview_threequarter.png\n` +
    `  CLAY: ${RAIN}/artifacts/${name}_clay/mview_front.png\n\n` +
    `Default to skepticism. If they were too generous (called a blobby/mismatched result good), lower it. ` +
    `If they were too harsh on a genuinely good clean result, raise it. ` +
    `Confirm whether glow is truly absent. Return your corrected assessment.`,
    { label: `verify:${name}`, phase: 'Verify', schema: VERIFY_SCHEMA }
  ).then(v => ({ review: rev, verify: v }))
)

const merged = CHARS.map(([name], i) => {
  const r = results[i]
  if (!r || !r.review) return { character: name, status: 'ERROR', overall: 0, redo: true, note: 'pipeline returned null' }
  const finalScore = (r.verify && typeof r.verify.correctedOverall === 'number') ? r.verify.correctedOverall : r.review.overall
  const finalRedo  = (r.verify && typeof r.verify.correctedRedo === 'boolean') ? r.verify.correctedRedo : r.review.redo
  return {
    character: name,
    finalScore, finalRedo,
    glowPresent: r.review.glowPresent,
    sub: { shape: r.review.shapeMatch, color: r.review.colorMatch, seams: r.review.seamDetail, head: r.review.headFace },
    issues: r.review.issues || [],
    verifyNote: r.verify ? r.verify.note : '',
    agree: r.verify ? r.verify.agree : null,
  }
})

log('Review complete: ' + merged.map(m => `${m.character}=${m.finalScore}${m.finalRedo ? '(REDO)' : ''}`).join(' '))
return merged
