---
id: knowledge-wellbeing-source-register-001
title: "Wellbeing Division — initial authoritative source register"
division: "wellbeing"
topics:
  - source-governance
  - evidence-hierarchy
  - uk-mental-health
  - clinical-safety
source:
  publisher: "AtlasOnePro Wellbeing Knowledge Division"
  title: "Initial source register with linked primary publishers"
  url: "https://github.com/quickchefbooking-ship-it/Project-atlas-"
  retrieved: "2026-11-13"
  source_type: "curated-source-index"
review_status: "curated-reference"
---

# Wellbeing Division — initial authoritative source register

**Purpose:** a controlled discovery list for Phase 1. This index is not a clinical guideline and does not automatically approve every page published by a listed organisation. Each individual item must be reviewed, versioned and approved before use in a user-facing answer.

## A. Priority one — UK clinical guidance and services

| Source ID | Publisher | Starting point | Intended use | Review rule |
|---|---|---|---|---|
| `nice-guidance` | NICE | https://www.nice.org.uk/guidance | Current clinical guidelines, recommendations, evidence reviews and quality standards | Capture guideline ID, population, recommendation section, publication/update/review dates and status. Check for updates before every release. |
| `nice-depression-ng222` | NICE | https://www.nice.org.uk/guidance/ng222 | Depression in adults: treatment and management | Use exact recommendation references; do not generalise to children or other conditions. |
| `nice-self-harm-ng225` | NICE | https://www.nice.org.uk/guidance/ng225 | Self-harm assessment, management and preventing recurrence | Explicitly preserve NICE guidance not to use scales or global risk categories to predict suicide/self-harm or decide access to care. |
| `nice-anxiety-cg113` | NICE | https://www.nice.org.uk/guidance/cg113 | Generalised anxiety disorder and panic disorder in adults | Record last update and any replacement guidance; adult scope only. |
| `nhs-mental-health` | NHS | https://www.nhs.uk/nhs-services/mental-health-services/ | Public mental-health information and service navigation | Use for public-facing signposting; verify local eligibility and service routes. |
| `nhs-talking-therapies` | NHS | https://www.nhs.uk/tests-and-treatments/talking-therapies/ | Explanation of talking therapies and access | Distinguish general information from local availability and clinical suitability. |
| `nhs-talking-therapies-find` | NHS | https://www.nhs.uk/nhs-services/mental-health-services/find-nhs-talking-therapies-for-anxiety-and-depression/ | England self-referral route for anxiety and depression | Verify current local pathway and age/GP-registration eligibility before signposting. |
| `nhs-urgent-mental-health` | NHS | https://www.nhs.uk/nhs-services/mental-health-services/where-to-get-urgent-help-for-mental-health/ | Urgent mental-health advice and emergency signposting | Recheck contact route and wording at least monthly and before each release. |
| `nhs-england-talking-therapies` | NHS England | https://www.england.nhs.uk/mental-health/adults/nhs-talking-therapies/ | Service model, access and delivery information | Use for service-level context; public signposting should also link to NHS.uk. |

## B. Priority two — international guidance and evidence synthesis

| Source ID | Publisher | Starting point | Intended use | Review rule |
|---|---|---|---|---|
| `who-mental-health` | WHO | https://www.who.int/health-topics/mental-health | Global public-health guidance and evidence-based resources | Record global context and avoid assuming UK service applicability. |
| `who-psychological-self-help-2026` | WHO | https://www.who.int/publications/i/item/9789240120785 | 2026 manual on individual psychological self-help, including Step-by-Step and Doing What Matters in Times of Stress | Check full document, programme population, delivery model, licence and implementation requirements before adapting exercises. |
| `cochrane-mental-health` | Cochrane | https://www.cochrane.org/evidence | Systematic reviews relevant to mental health and psychological interventions | Record review date, certainty, included population, heterogeneity and limitations; a review is not automatically a recommendation. |
| `pubmed-psychology` | US National Library of Medicine / PubMed | https://pubmed.ncbi.nlm.nih.gov/ | Discovery of peer-reviewed psychology and psychiatry research | Discovery only. Verify the original publication, study design, corrections/retractions and full abstract or article. |

## C. Priority three — professional bodies, patient information and regulatory guidance

| Source ID | Publisher | Starting point | Intended use | Review rule |
|---|---|---|---|---|
| `rcpsych-patient-info` | Royal College of Psychiatrists | https://www.rcpsych.ac.uk/mental-health | Readable, evidence-based patient and carer information | Patient education, not a substitute for NICE recommendations or individual assessment. |
| `bps` | British Psychological Society | https://www.bps.org.uk/ | Professional standards, ethics, practice and psychology resources | Record exact policy/code version and current status; do not imply BPS endorsement. |
| `hcpc` | Health and Care Professions Council | https://www.hcpc-uk.org/ | Registration and standards for regulated practitioner groups within its remit | Use to verify relevant professional registration and standards, not to imply every therapist is HCPC-regulated. |
| `gmc` | General Medical Council | https://www.gmc-uk.org/ | Medical practitioner registration and professional standards | Verify registration and relevant scope. |
| `mhra-dmht` | MHRA | https://www.gov.uk/government/publications/digital-mental-health-technology-qualification-and-classification | Qualification and classification of digital mental-health technology | Mandatory regulatory review before intended-purpose or clinical claims changes. |
| `mhra-samd` | MHRA | https://www.gov.uk/government/publications/software-and-artificial-intelligence-ai-as-a-medical-device | Software/AI as a medical device | Review current guidance and legislation; obtain specialist regulatory advice. |
| `ico-special-category` | Information Commissioner's Office | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/ | UK GDPR special-category health data | Identify Article 6 basis and Article 9 condition, safeguards and DPIA obligations before processing. |

## D. Evidence-source record requirements

For every individual document retrieved from these sources, store:
- canonical URL or DOI and publisher;
- title, authoring body and source ID;
- source type and evidence class;
- publication, update, retrieval and review dates separately;
- population, age range, jurisdiction and exclusions;
- exact section, recommendation or page used;
- study design, sample and limitations where relevant;
- guideline status, version and supersession relationship;
- SHA-256 content hash and permitted reuse/licence status;
- Source Division state and separate wellbeing clinical review state;
- reviewer identity, credentials verification reference, decision rationale and next review date.

## E. Initial source checks completed for this specification

The following pages were checked during preparation on 13 November 2026. These checks establish that the links resolve and provide the stated starting point; they do not constitute formal clinical approval of a knowledge item.

1. NICE NG222, Depression in adults: treatment and management — https://www.nice.org.uk/guidance/ng222/chapter/Recommendations
2. NICE NG225, Self-harm: assessment, management and preventing recurrence — https://www.nice.org.uk/guidance/ng225
3. NICE CG113, Generalised anxiety disorder and panic disorder in adults — https://www.nice.org.uk/guidance/cg113
4. NHS Talking therapies — https://www.nhs.uk/tests-and-treatments/talking-therapies/
5. NHS find NHS Talking Therapies — https://www.nhs.uk/nhs-services/mental-health-services/find-nhs-talking-therapies-for-anxiety-and-depression/
6. NHS urgent mental-health help — https://www.nhs.uk/nhs-services/mental-health-services/where-to-get-urgent-help-for-mental-health/
7. NHS England Talking Therapies — https://www.england.nhs.uk/mental-health/adults/nhs-talking-therapies/
8. WHO, Psychological self-help interventions (published 1 June 2026) — https://www.who.int/publications/i/item/9789240120785
9. Royal College of Psychiatrists mental-health information — https://www.rcpsych.ac.uk/mental-health/
10. MHRA, Digital mental health technology: qualification and classification (updated 29 July 2026) — https://www.gov.uk/government/publications/digital-mental-health-technology-qualification-and-classification
11. ICO, Special category data (updated October 2026) — https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/

Cochrane, PubMed and professional-body resources are included as priority discovery sources. Individual review articles, codes and standards must be selected and checked separately; this register does not imply that a particular Cochrane review or BPS code has already been approved.

## F. Maintenance

- Recheck urgent service routes monthly and before every release.
- Recheck NICE, NHS, WHO and MHRA updates at least quarterly, and before any relevant release.
- Recheck every approved guideline on its published review/update date.
- Quarantine sources with broken links, superseded recommendations, retractions, unresolved conflicts or unknown provenance.
- Keep historical versions for audit, but never retrieve expired/superseded items for current user-facing guidance.
