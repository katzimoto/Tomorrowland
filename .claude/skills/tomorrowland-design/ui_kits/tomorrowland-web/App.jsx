/* global React, ReactDOM, NavRail, SignIn, SearchView, DocumentView, ChatView */

function App() {
  const [signedIn, setSignedIn] = React.useState(true);
  const [expired, setExpired] = React.useState(false);
  const [view, setView] = React.useState("search"); // 'search' | 'document' | 'chat' | 'subscriptions' | etc
  const [openDocId, setOpenDocId] = React.useState(null);
  const [chatDocId, setChatDocId] = React.useState(null);
  const [railExpanded, setRailExpanded] = React.useState(true);

  const user = { name: "Operations · Tanaka", email: "ops@acme.local" };

  function navigate(key) {
    if (key === "chat") setChatDocId(null);
    setOpenDocId(null);
    setView(key);
  }

  if (!signedIn) {
    return <SignIn expired={expired} onSignIn={() => { setSignedIn(true); setExpired(false); }} />;
  }

  let content;
  if (view === "document" && openDocId) {
    content = (
      <DocumentView
        docId={openDocId}
        onBack={() => { setOpenDocId(null); setView("search"); }}
        onOpenChat={(id) => { setChatDocId(id); setView("chat"); }}
      />
    );
  } else if (view === "chat") {
    content = <ChatView scopeDocId={chatDocId} />;
  } else if (view === "search") {
    content = (
      <SearchView
        onOpenDocument={(id) => { setOpenDocId(id); setView("document"); }}
      />
    );
  } else {
    // Other rail destinations — show a faithful empty/coming-soon state in the
    // product's voice rather than mocking a half-built screen.
    const titles = {
      subscriptions: ["Subscriptions", "Create one from scratch or subscribe to a saved search."],
      notifications: ["Notifications", "You'll be notified here when documents match your subscriptions."],
      history: ["History", "Documents you view will appear here."],
      expertise: ["Expertise map", "Find colleagues through document evidence. Results are not rankings or performance scores."],
    };
    const [t, b] = titles[view] || ["Tomorrowland", ""];
    content = (
      <div className="search-page" data-screen-label={t}>
        <header className="search-header">
          <h1 className="search-title">{t}</h1>
        </header>
        <div className="empty">
          <h2>Nothing yet</h2>
          <p>{b}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <NavRail
        active={view}
        onNavigate={navigate}
        onSignOut={() => { setSignedIn(false); setExpired(true); }}
        expanded={railExpanded}
        onToggle={() => setRailExpanded((e) => !e)}
        user={user}
      />
      <main className="main">{content}</main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
