import { createRouter, createRoute, createRootRoute, redirect } from "@tanstack/react-router";
import { authStorage } from "@/api/auth";
import { LoginPage } from "@/features/auth/LoginPage";
import { SearchPage } from "@/features/search/SearchPage";
import { DocumentPage } from "@/features/documents/DocumentPage";
import { QAPage } from "@/features/qa/QAPage";
import { SubscriptionsPage } from "@/features/subscriptions/SubscriptionsPage";
import { NotificationsPage } from "@/features/notifications/NotificationsPage";
import { HistoryPage } from "@/features/history/HistoryPage";
import { ExpertisePage } from "@/features/expertise/ExpertisePage";
import { AdminSourcesPage } from "@/features/admin/AdminSourcesPage";
import { AppLayout } from "./AppLayout";
import { PlaceholderPage } from "./PlaceholderPage";

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

const docRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/doc/$docId",
  component: DocumentPage,
});

const qaRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/qa",
  component: QAPage,
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

const settingsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/settings/profile",
  component: () => <PlaceholderPage title="Settings" />,
});

const adminRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin",
  component: AdminSourcesPage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  appRoute.addChildren([
    indexRoute,
    searchRoute,
    docRoute,
    qaRoute,
    subscriptionsRoute,
    notificationsRoute,
    historyRoute,
    expertiseRoute,
    settingsRoute,
    adminRoute,
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
