import { lazy, Suspense } from "react";
import { createRouter, createRoute, createRootRoute, redirect } from "@tanstack/react-router";
import { authStorage } from "@/api/auth";
import { AppLayout } from "./AppLayout";

// --- Route-level code splitting ---
// Auth pages sit outside AppLayout so they carry their own Suspense wrapper.
// App pages render inside AppLayout whose <Outlet> is already wrapped in Suspense.

const LazyLoginPage    = lazy(() => import("@/features/auth/LoginPage").then(m => ({ default: m.LoginPage })));
const LazySignUpPage   = lazy(() => import("@/features/auth/SignUpPage").then(m => ({ default: m.SignUpPage })));
const LazySearchPage   = lazy(() => import("@/features/search/SearchPage").then(m => ({ default: m.SearchPage })));
const LazyDocumentPage = lazy(() => import("@/features/documents/DocumentPage").then(m => ({ default: m.DocumentPage })));
const LazyChatPage     = lazy(() => import("@/features/chat/ChatPage").then(m => ({ default: m.ChatPage })));
const LazySubscriptionsPage   = lazy(() => import("@/features/subscriptions/SubscriptionsPage").then(m => ({ default: m.SubscriptionsPage })));
const LazyNotificationsPage   = lazy(() => import("@/features/notifications/NotificationsPage").then(m => ({ default: m.NotificationsPage })));
const LazyHistoryPage  = lazy(() => import("@/features/history/HistoryPage").then(m => ({ default: m.HistoryPage })));
const LazyExpertisePage = lazy(() => import("@/features/expertise/ExpertisePage").then(m => ({ default: m.ExpertisePage })));
const LazyAdminHubPage         = lazy(() => import("@/features/admin/AdminHubPage").then(m => ({ default: m.AdminHubPage })));
const LazyAdminIngestionPage   = lazy(() => import("@/features/admin/AdminIngestionPage").then(m => ({ default: m.AdminIngestionPage })));
const LazyAdminSourcesPage     = lazy(() => import("@/features/admin/AdminSourcesPage").then(m => ({ default: m.AdminSourcesPage })));
const LazyAdminSourceDetailPage = lazy(() => import("@/features/admin/AdminSourceDetailPage").then(m => ({ default: m.AdminSourceDetailPage })));
const LazyAdminAddSourceWizard  = lazy(() => import("@/features/admin/AdminAddSourceWizard").then(m => ({ default: m.AdminAddSourceWizard })));
const LazyAdminEditSourcePage   = lazy(() => import("@/features/admin/AdminEditSourcePage").then(m => ({ default: m.AdminEditSourcePage })));
const LazyAdminGroupsPage       = lazy(() => import("@/features/admin/AdminGroupsPage").then(m => ({ default: m.AdminGroupsPage })));
const LazyAdminGroupDetailPage  = lazy(() => import("@/features/admin/AdminGroupDetailPage").then(m => ({ default: m.AdminGroupDetailPage })));
const LazyAdminUsersPage        = lazy(() => import("@/features/admin/AdminUsersPage").then(m => ({ default: m.AdminUsersPage })));
const LazyAdminUserDetailPage   = lazy(() => import("@/features/admin/AdminUserDetailPage").then(m => ({ default: m.AdminUserDetailPage })));

// Auth pages need their own Suspense boundary (no AppLayout shell above them).
function LoginPage()  { return <Suspense fallback={null}><LazyLoginPage /></Suspense>; }
function SignUpPage() { return <Suspense fallback={null}><LazySignUpPage /></Suspense>; }

// App pages delegate to AppLayout's Suspense-wrapped Outlet.
const SearchPage            = LazySearchPage;
const DocumentPage          = LazyDocumentPage;
const ChatPage              = LazyChatPage;
const SubscriptionsPage     = LazySubscriptionsPage;
const NotificationsPage     = LazyNotificationsPage;
const HistoryPage           = LazyHistoryPage;
const ExpertisePage         = LazyExpertisePage;
const AdminHubPage          = LazyAdminHubPage;
const AdminIngestionPage    = LazyAdminIngestionPage;
const AdminSourcesPage      = LazyAdminSourcesPage;
const AdminSourceDetailPage = LazyAdminSourceDetailPage;
const AdminAddSourceWizard  = LazyAdminAddSourceWizard;
const AdminEditSourcePage   = LazyAdminEditSourcePage;
const AdminGroupsPage       = LazyAdminGroupsPage;
const AdminGroupDetailPage  = LazyAdminGroupDetailPage;
const AdminUsersPage        = LazyAdminUsersPage;
const AdminUserDetailPage   = LazyAdminUserDetailPage;

function requireAuth() {
  if (!authStorage.hasToken()) {
    throw redirect({ to: "/login" });
  }
}

const rootRoute = createRootRoute();

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
});

const signupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/signup",
  component: SignUpPage,
});

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "app",
  beforeLoad: requireAuth,
  component: AppLayout,
});

const indexRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/",
  beforeLoad: () => { throw redirect({ to: "/search", search: { q: "", mode: "hybrid" } }); },
});

const searchRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/search",
  component: SearchPage,
  validateSearch: (search: Record<string, unknown>) => ({
    q: typeof search.q === "string" ? search.q : "",
    mode: typeof search.mode === "string" ? search.mode : "hybrid",
  }),
});

function parseNum(v: unknown): number | undefined {
  if (typeof v === "number") return v;
  if (typeof v === "string") {
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  }
  return undefined;
}

const docRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/doc/$docId",
  component: DocumentPage,
  validateSearch: (search: Record<string, unknown>) => {
    const page = parseNum(search.page);
    const chunk = parseNum(search.chunk);
    return { ...(page !== undefined ? { page } : {}), ...(chunk !== undefined ? { chunk } : {}) };
  },
});

const chatRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/chat",
  component: ChatPage,
  validateSearch: (search: Record<string, unknown>) => ({
    scope: typeof search.scope === "string" ? search.scope : undefined,
    ids: typeof search.ids === "string" ? search.ids : undefined,
  }),
});

const subscriptionsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/subscriptions",
  component: SubscriptionsPage,
});

const notificationsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/notifications",
  component: NotificationsPage,
});

const historyRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/history",
  component: HistoryPage,
});

const expertiseRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/expertise",
  component: ExpertisePage,
});

const adminRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin",
  component: AdminHubPage,
});

const adminIngestionRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/ingestion",
  component: AdminIngestionPage,
});

const adminSourcesRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/sources",
  component: AdminSourcesPage,
});

const adminAddSourceRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/sources/new",
  component: AdminAddSourceWizard,
});

const adminSourceDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/sources/$sourceId",
  component: AdminSourceDetailPage,
});

const adminEditSourceRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/sources/$sourceId/edit",
  component: AdminEditSourcePage,
});

const adminGroupsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/groups",
  component: AdminGroupsPage,
});

const adminGroupDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/groups/$groupId",
  component: AdminGroupDetailPage,
});

const adminUsersRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/users",
  component: AdminUsersPage,
});

const adminUserDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/users/$userId",
  component: AdminUserDetailPage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  signupRoute,
  appRoute.addChildren([
    indexRoute,
    searchRoute,
    docRoute,
    chatRoute,
    subscriptionsRoute,
    notificationsRoute,
    historyRoute,
    expertiseRoute,
    adminRoute,
    adminIngestionRoute,
    adminSourcesRoute,
    adminAddSourceRoute,
    adminSourceDetailRoute,
    adminEditSourceRoute,
    adminGroupsRoute,
    adminGroupDetailRoute,
    adminUsersRoute,
    adminUserDetailRoute,
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
