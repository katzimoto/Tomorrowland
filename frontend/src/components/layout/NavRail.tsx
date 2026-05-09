import { useState, useEffect } from "react";
import { Link } from "@tanstack/react-router";
import {
  Search,
  MessageSquare,
  Bell,
  History,
  Bookmark,
  Settings,
  Shield,
  ChevronRight,
  ChevronLeft,
} from "lucide-react";
import styles from "./NavRail.module.css";

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/search", label: "Search", icon: <Search size={20} /> },
  { to: "/qa", label: "Q&A", icon: <MessageSquare size={20} /> },
  { to: "/subscriptions", label: "Subscriptions", icon: <Bookmark size={20} /> },
  { to: "/notifications", label: "Notifications", icon: <Bell size={20} /> },
  { to: "/history", label: "History", icon: <History size={20} /> },
];

const ADMIN_ITEM: NavItem = {
  to: "/admin",
  label: "Admin",
  icon: <Shield size={20} />,
};

const STORAGE_KEY = "neverland_rail_expanded";

interface NavRailProps {
  isAdmin: boolean;
  unreadCount?: number;
}

export function NavRail({ isAdmin, unreadCount = 0 }: NavRailProps) {
  const [expanded, setExpanded] = useState<boolean>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, expanded ? "1" : "0");
    } catch {
      // ignore storage errors in sandboxed environments
    }
  }, [expanded]);

  const items = isAdmin ? [...NAV_ITEMS, ADMIN_ITEM] : NAV_ITEMS;

  return (
    <nav
      className={`${styles.rail} ${expanded ? styles.expanded : ""}`}
      aria-label="Primary navigation"
    >
      <div className={styles.top}>
        <div className={styles.mark} aria-label="Neverland">N</div>
        <button
          className={styles.toggle}
          onClick={() => setExpanded((e) => !e)}
          aria-label={expanded ? "Collapse navigation" : "Expand navigation"}
          title={expanded ? "Collapse navigation" : "Expand navigation"}
        >
          {expanded ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>

      <ul className={styles.list} role="list">
        {items.map((item) => (
          <li key={item.to}>
            <Link
              to={item.to}
              className={styles.item}
              activeProps={{ className: `${styles.item} ${styles.active}` }}
              title={!expanded ? item.label : undefined}
            >
              <span className={styles.icon} aria-hidden>
                {item.to === "/notifications" && unreadCount > 0 ? (
                  <span className={styles.badgeWrap}>
                    {item.icon}
                    <span className={styles.badge} aria-label={`${unreadCount} unread`}>
                      {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                  </span>
                ) : (
                  item.icon
                )}
              </span>
              <span className={styles.label}>{item.label}</span>
            </Link>
          </li>
        ))}
      </ul>

      <div className={styles.bottom}>
        <Link
          to="/settings/profile"
          className={styles.item}
          title={!expanded ? "Settings" : undefined}
        >
          <span className={styles.icon} aria-hidden><Settings size={20} /></span>
          <span className={styles.label}>Settings</span>
        </Link>
      </div>
    </nav>
  );
}
