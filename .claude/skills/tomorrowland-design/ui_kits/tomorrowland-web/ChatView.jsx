/* global React, Icon, Button, CHAT_SESSIONS, STARTERS, DOCUMENTS */

function Bubble({ role, children, ground }) {
  return (
    <div className={`bubble ${role}`}>
      {children}
      {ground && <p className="ground">Based only on documents you can access.</p>}
    </div>
  );
}

function Citation({ index, title, location }) {
  return (
    <div className="citation">
      <span className="idx">[{index}]</span>
      <div>
        <div className="title">{title}</div>
        <div className="loc">{location}</div>
      </div>
    </div>
  );
}

function ChatView({ scopeDocId }) {
  const [activeId, setActiveId] = React.useState(scopeDocId ? "new" : "c1");
  const [draft, setDraft] = React.useState("");
  const [messages, setMessages] = React.useState(() => {
    if (scopeDocId) return [];
    return [
      { role: "user", text: "Which runbook covers a paged Sev-1 outside business hours?" },
      {
        role: "assistant",
        text: "The on-call engineer follows the Incident response runbook — Q3 2025. For pages received outside 09:00–18:00 local, the coordinator escalates to the secondary on-call after ten minutes without acknowledgement.",
        ground: true,
        citations: [
          { title: "Incident response runbook — Q3 2025", location: "Confluence · §2 Out-of-hours escalation" },
          { title: "Platform on-call rota — Aug 2025", location: "Confluence · Top of page" },
        ],
      },
    ];
  });

  const composerRef = React.useRef(null);

  React.useEffect(() => {
    if (composerRef.current) {
      composerRef.current.style.height = "auto";
      composerRef.current.style.height = Math.min(composerRef.current.scrollHeight, 160) + "px";
    }
  }, [draft]);

  function send(text) {
    const t = (text ?? draft).trim();
    if (!t) return;
    setDraft("");
    setMessages((m) => [...m, { role: "user", text: t }]);
    setTimeout(() => {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: "Based on the accessible documents, the on-call rota for the Platform team runs Mon 09:00 → following Mon 09:00 local. Handover happens at the Monday standup with a written one-pager.",
          ground: true,
          citations: [
            { title: "Platform on-call rota — Aug 2025", location: "Confluence · Top of page" },
          ],
        },
      ]);
    }, 350);
  }

  const scopeDoc = scopeDocId ? DOCUMENTS.find((d) => d.id === scopeDocId) : null;

  return (
    <div className="chat-page" data-screen-label="Chat">
      <div className="chat-header">
        <h1>Document Chat</h1>
        <Button variant="secondary" size="sm">
          <Icon name="plus" size={14} /> New chat
        </Button>
      </div>

      <div className="chat-body">
        <aside className="chat-sidebar">
          <div className="chat-sidebar-top">
            <Button variant="secondary" style={{ width: "100%" }}>
              <Icon name="plus" size={14} /> New chat
            </Button>
          </div>
          <ul className="chat-list">
            {CHAT_SESSIONS.map((c) => (
              <li key={c.id} className={`chat-item${activeId === c.id ? " active" : ""}`}>
                <button className="chat-item-btn" onClick={() => setActiveId(c.id)}>
                  <span className="chat-item-title">{c.title}</span>
                  <span className="chat-item-time">{c.time}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <div className="chat-main">
          {scopeDoc && (
            <div className="scope-bar">
              <span className="label">Chatting with</span>
              <span className="value">{scopeDoc.title}</span>
              <span style={{ marginLeft: "auto" }}>
                <Button variant="ghost" size="sm">Change scope</Button>
              </span>
            </div>
          )}

          {messages.length === 0 ? (
            <>
              <div className="starter">
                <div className="starter-heading">
                  {scopeDoc
                    ? `Ask questions about “${scopeDoc.title}”. Answers cite this document only.`
                    : "Ask questions about your documents. Answers are based only on documents you can access, with sources."}
                </div>
                <div className="starter-grid">
                  {STARTERS.map((s) => (
                    <button key={s} className="starter-pill" onClick={() => send(s)}>{s}</button>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="chat-stream">
              {messages.map((m, i) => (
                <React.Fragment key={i}>
                  <Bubble role={m.role} ground={m.ground}>{m.text}</Bubble>
                  {m.citations && (
                    <>
                      <div className="sources-heading">Sources</div>
                      {m.citations.map((c, j) => (
                        <Citation key={j} index={j + 1} title={c.title} location={c.location} />
                      ))}
                    </>
                  )}
                </React.Fragment>
              ))}
            </div>
          )}

          <div className="composer-row">
            <textarea
              ref={composerRef}
              className="composer"
              placeholder="Ask a question…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <Button onClick={() => send()} disabled={!draft.trim()}>
              <Icon name="send" size={14} /> Send
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

window.ChatView = ChatView;
