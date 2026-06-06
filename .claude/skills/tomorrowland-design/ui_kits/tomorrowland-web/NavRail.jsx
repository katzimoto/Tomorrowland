/* global React, Icon */

const NAV_ITEMS = [
  { to: "search", key: "search", label: "Search", icon: "search" },
  { to: "chat", key: "chat", label: "Chat", icon: "messages" },
  { to: "subscriptions", key: "subscriptions", label: "Subscriptions", icon: "bookmark" },
  { to: "notifications", key: "notifications", label: "Notifications", icon: "bell" },
  { to: "history", key: "history", label: "History", icon: "history" },
  { to: "expertise", key: "expertise", label: "Expertise", icon: "network" },
];

function NavRail({ active, onNavigate, onSignOut, expanded, onToggle, unread = 3, user }) {
  return (
    <nav className={`rail ${expanded ? "expanded" : ""}`} aria-label="Primary navigation">
      <div className="rail-top">
        <img className="rail-mark" src="../../assets/favicon.svg" alt="Tomorrowland logo" />
        <button className="rail-toggle" onClick={onToggle} aria-label={expanded ? "Collapse navigation" : "Expand navigation"}>
          <Icon name={expanded ? "chevron-left" : "chevron-right"} size={16} />
        </button>
      </div>

      <ul className="rail-list" role="list">
        {NAV_ITEMS.map((item) => (
          <li key={item.key}>
            <button
              className={`rail-item ${active === item.key ? "active" : ""}`}
              onClick={() => onNavigate?.(item.key)}
              title={expanded ? undefined : item.label}
            >
              <span className="rail-icn">
                {item.key === "notifications" && unread > 0 ? (
                  <span className="rail-badge-wrap">
                    <Icon name={item.icon} />
                    <span className="rail-badge">{unread > 9 ? "9+" : unread}</span>
                  </span>
                ) : (
                  <Icon name={item.icon} />
                )}
              </span>
              <span className="rail-label">{item.label}</span>
            </button>
          </li>
        ))}
      </ul>

      <div className="rail-bottom">
        {user && expanded && (
          <div className="rail-user">
            <span className="rail-user-name">{user.name}</span>
            <span className="rail-user-email">{user.email}</span>
          </div>
        )}
        <button className="rail-item" onClick={onSignOut} title={expanded ? undefined : "Sign out"}>
          <span className="rail-icn"><Icon name="log-out" /></span>
          <span className="rail-label">Sign out</span>
        </button>
      </div>
    </nav>
  );
}

window.NavRail = NavRail;
