/* global React */
// Mock corpus + chat data — small, hand-curated. Replaces the API.

const SOURCES = [
  { id: "src-confluence", label: "Confluence", type: "confluence" },
  { id: "src-jira", label: "Jira", type: "jira" },
  { id: "src-legal", label: "Legal Docs", type: "folder" },
  { id: "src-eng", label: "Engineering Wiki", type: "folder" },
];

const DOCUMENTS = [
  {
    id: "doc-runbook",
    title: "Incident response runbook — Q3 2025",
    source: "Confluence",
    sourceId: "src-confluence",
    mime: "application/pdf",
    updated: "2025-05-21",
    updatedLabel: "4 days ago",
    tags: ["runbook", "sev-1", "oncall"],
    extraTagCount: 2,
    translation: "high",
    snippet:
      "…the on-call engineer SHOULD declare a Sev-1 <mark>incident</mark> within five minutes of paging. The <mark>response</mark> coordinator then opens the war room and broadcasts in #incident-coord…",
    summary:
      "Defines the operator playbook for Sev-1 incidents — paging path, declaration timeline, war-room conventions, and post-mortem expectations. Effective 2025-07-01.",
    entities: ["PagerDuty", "Sev-1", "war room", "#incident-coord", "Q3 2025"],
    body: [
      { type: "h1", text: "Incident response runbook — Q3 2025" },
      { type: "p", text: "This runbook applies to all production services owned by the Platform organisation. It supersedes the 2024-Q4 revision; on conflict, this document governs." },
      { type: "h2", text: "1. Severity declaration" },
      { type: "p", text: "On any user-visible outage of a tier-0 surface, the on-call engineer declares a Sev-1 within five minutes of being paged. Declaration is performed by typing /sev1 in #incident-coord; the bot opens a war room and notifies the response coordinator." },
      { type: "h2", text: "2. Out-of-hours escalation" },
      { type: "p", text: "For pages received outside 09:00–18:00 local, the coordinator escalates to the secondary on-call after ten minutes without acknowledgement. If the secondary has not acknowledged within a further five minutes, the team manager is paged directly." },
      { type: "h2", text: "3. War room conventions" },
      { type: "p", text: "Exactly one Incident Commander at any time. The IC delegates Comms, Ops, and Scribe. Speak in present tense. Restate decisions explicitly so the scribe can capture them." },
    ],
  },
  {
    id: "doc-dpa",
    title: "2024 DPA — ACME ↔ Westwind (executed)",
    source: "Legal Docs",
    sourceId: "src-legal",
    mime: "application/pdf",
    updated: "2025-03-14",
    updatedLabel: "Mar 14, 2025",
    tags: ["gdpr", "contract"],
    extraTagCount: 0,
    translation: null,
    snippet:
      "…the processor SHALL implement appropriate technical and organisational measures to ensure a level of security appropriate to the risk, including pseudonymisation, encryption…",
    summary:
      "Data Processing Agreement between ACME (controller) and Westwind (processor) governing personal-data handling. Annexes I–III enumerate sub-processors, security measures, and processing instructions.",
    entities: ["ACME Holdings", "Westwind Ltd", "Annex I", "Annex II", "Article 28 GDPR"],
    body: [
      { type: "h1", text: "Data Processing Agreement" },
      { type: "p", text: "This Data Processing Agreement (\u201cDPA\u201d) forms part of the Master Services Agreement entered into between ACME Holdings (\u201cController\u201d) and Westwind Ltd (\u201cProcessor\u201d) effective 14 March 2025." },
      { type: "h2", text: "1. Subject matter" },
      { type: "p", text: "The Processor shall process Personal Data on behalf of the Controller for the purposes set out in Annex I and for no other purpose." },
      { type: "h2", text: "2. Security measures" },
      { type: "p", text: "The Processor shall implement appropriate technical and organisational measures to ensure a level of security appropriate to the risk, including pseudonymisation, encryption, and the ability to restore availability following a physical or technical incident." },
    ],
  },
  {
    id: "doc-rota",
    title: "On-call rota — Platform team — Aug 2025",
    source: "Confluence",
    sourceId: "src-confluence",
    mime: "text/html",
    updated: "2025-05-19",
    updatedLabel: "6 days ago",
    tags: ["oncall", "rota"],
    extraTagCount: 0,
    translation: null,
    snippet:
      "Primary and secondary <mark>on-call</mark> shifts run Mon 09:00 → following Mon 09:00 local. Handover at the Monday standup with a written one-pager in #plat-handover…",
    summary: "Weekly on-call rota for the Platform team. Effective August 2025. Includes handover protocol and swap rules.",
    entities: ["Platform team", "#plat-handover", "Monday standup"],
    body: [
      { type: "h1", text: "Platform on-call rota — August 2025" },
      { type: "p", text: "Primary and secondary on-call shifts run Mon 09:00 → following Mon 09:00 local. Handover at the Monday standup, with a written one-pager in #plat-handover." },
    ],
  },
  {
    id: "doc-ticket",
    title: "PLAT-4821 — Elasticsearch indexer stalls on >2GB attachments",
    source: "Jira",
    sourceId: "src-jira",
    mime: "text/html",
    updated: "2025-05-20",
    updatedLabel: "5 days ago",
    tags: ["sev-2", "indexer", "bug"],
    extraTagCount: 0,
    translation: null,
    snippet:
      "Reproduction: ingest a PDF larger than 2&nbsp;GB. The <mark>indexer</mark> worker holds the connection open but never emits a chunk_ingested event…",
    summary: "Sev-2 bug in the slow-path indexer worker. Workaround documented in the ticket; permanent fix tracked in PLAT-4839.",
    entities: ["PLAT-4821", "PLAT-4839", "Elasticsearch"],
    body: [
      { type: "h1", text: "PLAT-4821 — Elasticsearch indexer stalls on >2GB attachments" },
      { type: "p", text: "Reproduction: ingest a PDF larger than 2 GB. The indexer worker holds the connection open but never emits a chunk_ingested event, blocking the source's progress cursor." },
    ],
  },
  {
    id: "doc-translation",
    title: "ISO/IEC 27001:2022 control mapping (DE → EN)",
    source: "Legal Docs",
    sourceId: "src-legal",
    mime: "application/pdf",
    updated: "2025-04-02",
    updatedLabel: "Apr 2, 2025",
    tags: ["iso27001", "compliance"],
    extraTagCount: 1,
    translation: "fast",
    snippet:
      "Mapping of Annex A controls against internal practice. The translated copy is suitable for first-pass review only; refer to the original German document for audit evidence.",
    summary:
      "First-pass machine translation of the German ISO/IEC 27001:2022 control mapping. Use the original for any audit-of-record purpose.",
    entities: ["ISO/IEC 27001:2022", "Annex A", "BSI"],
    body: [
      { type: "h1", text: "ISO/IEC 27001:2022 control mapping" },
      { type: "p", text: "Translated from the German original. For audit evidence, refer to the original document — this version is provided for first-pass review only." },
    ],
  },
];

const CHAT_SESSIONS = [
  { id: "c1", title: "Sev-1 escalation flow", time: "Today, 11:42" },
  { id: "c2", title: "GDPR DPA — annex II questions", time: "Yesterday" },
  { id: "c3", title: "Platform on-call rota — Aug", time: "Mon" },
  { id: "c4", title: "Indexer stalls > 2GB attachments", time: "May 20" },
];

const STARTERS = [
  "What changed in the new on-call rota?",
  "Summarise the Q3 incident runbook",
  "List open Jira incidents tagged sev-1",
  "Which annex of the DPA covers sub-processors?",
];

Object.assign(window, { SOURCES, DOCUMENTS, CHAT_SESSIONS, STARTERS });
